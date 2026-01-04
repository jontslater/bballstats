"""
Player Team Sync Service

Syncs player team assignments from recent game stats to catch trades and team changes.
Also uses NBA API rosters as a fallback for up-to-date team assignments.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from typing import Dict, List, Optional
from datetime import date, timedelta
from app.models.player import Player
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.team import Team


class PlayerTeamSyncService:
    """Service for syncing player team assignments from game stats."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def sync_all_players(self, days_back: int = 30, use_nba_api: bool = True) -> Dict[str, int]:
        """
        Sync all players' team assignments from recent game stats.
        Falls back to NBA API rosters if game stats aren't available.
        
        Args:
            days_back: Number of days to look back for recent games
            use_nba_api: Whether to use NBA API rosters as fallback
        
        Returns:
            Dict with counts of players updated, unchanged, and errors
        """
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Get all players
        all_players = self.db.query(Player).all()
        
        updated_count = 0
        unchanged_count = 0
        error_count = 0
        api_updated = 0
        
        # ENHANCEMENT: Get current rosters from NBA API as fallback
        nba_api_rosters = {}
        if use_nba_api:
            try:
                from app.scrapers.nba_api_client import NBAAPIClient
                client = NBAAPIClient(delay=1.0)
                
                # Get all teams
                teams = self.db.query(Team).all()
                print(f"  Fetching current rosters from NBA API for {len(teams)} teams...")
                
                for team in teams:
                    try:
                        # Get roster from NBA API using team abbreviation
                        roster = self._get_team_roster_from_api(client, team.abbreviation)
                        if roster:
                            nba_api_rosters[team.team_id] = roster
                            print(f"    ✅ {team.abbreviation}: {len(roster)} players")
                    except Exception as e:
                        print(f"    ⚠️  {team.abbreviation}: Error fetching roster - {e}")
                        continue
                
                print(f"  ✅ Fetched rosters for {len(nba_api_rosters)} teams")
            except Exception as e:
                print(f"  ⚠️  Could not fetch NBA API rosters: {e}")
                nba_api_rosters = {}
        
        for player in all_players:
            try:
                # First, try to get team from recent game stats
                most_recent_stat = self.db.query(PlayerGameStat).join(Game).filter(
                    and_(
                        PlayerGameStat.player_id == player.player_id,
                        Game.game_date >= cutoff_date,
                        Game.game_status == 'finished',
                        PlayerGameStat.minutes_played > 0  # Only games where they actually played
                    )
                ).order_by(desc(Game.game_date)).first()
                
                new_team_id = None
                update_source = None
                
                # IMPROVED: Prefer NBA API rosters as primary source (more reliable)
                # Then use game stats as fallback/validation
                if nba_api_rosters:
                    # Primary: Check NBA API rosters (most reliable for current team)
                    new_team_id = self._find_player_in_rosters(player, nba_api_rosters)
                    if new_team_id:
                        update_source = "nba_api"
                
                # Fallback: Use game stats if NBA API didn't find the player
                if not new_team_id and most_recent_stat:
                    # Use team from most recent game (only if game was recent - within last 30 days)
                    # Increased from 7 to 30 days to catch more cases
                    days_since_game = (date.today() - most_recent_stat.game.game_date).days
                    if days_since_game <= 30:
                        # Use majority vote from recent games for better accuracy
                        recent_stats = self.db.query(PlayerGameStat).join(Game).filter(
                            and_(
                                PlayerGameStat.player_id == player.player_id,
                                Game.game_date >= cutoff_date,
                                Game.game_status == 'finished',
                                PlayerGameStat.minutes_played > 0
                            )
                        ).order_by(desc(Game.game_date)).limit(10).all()
                        
                        if recent_stats:
                            # Count teams from recent games
                            team_counts = {}
                            for stat in recent_stats:
                                team_id = stat.team_id
                                team_counts[team_id] = team_counts.get(team_id, 0) + 1
                            
                            # Use team with most appearances (majority vote)
                            if team_counts:
                                new_team_id = max(team_counts.items(), key=lambda x: x[1])[0]
                                update_source = "game_stats_majority"
                
                if new_team_id and player.current_team_id != new_team_id:
                    old_team = self.db.query(Team).filter(Team.team_id == player.current_team_id).first() if player.current_team_id else None
                    new_team = self.db.query(Team).filter(Team.team_id == new_team_id).first()
                    
                    if new_team:
                        player.current_team_id = new_team_id
                        updated_count += 1
                        if update_source == "nba_api":
                            api_updated += 1
                        
                        if old_team:
                            print(f"  Updated {player.name}: {old_team.abbreviation} -> {new_team.abbreviation} ({update_source})")
                        else:
                            print(f"  Updated {player.name}: None -> {new_team.abbreviation} ({update_source})")
                    else:
                        unchanged_count += 1
                else:
                    unchanged_count += 1
                    
            except Exception as e:
                print(f"  Error syncing {player.name}: {e}")
                error_count += 1
        
        self.db.commit()
        
        return {
            'updated': updated_count,
            'api_updated': api_updated,
            'unchanged': unchanged_count,
            'errors': error_count,
            'total': len(all_players)
        }
    
    def _get_team_roster_from_api(self, client, team_abbreviation: str) -> Optional[List[Dict]]:
        """Get current team roster from NBA API using team abbreviation."""
        try:
            from nba_api.stats.endpoints import commonteamroster
            from nba_api.stats.static import teams as nba_teams
            
            # Map team abbreviation to NBA API team ID
            nba_team_id = None
            for team in nba_teams.get_teams():
                if team['abbreviation'] == team_abbreviation:
                    nba_team_id = team['id']
                    break
            
            if not nba_team_id:
                return None
            
            self._rate_limit()
            roster = commonteamroster.CommonTeamRoster(
                team_id=nba_team_id,
                season='2024-25',  # Current season
                timeout=30
            )
            
            # Get roster data
            roster_df = roster.get_data_frames()[0]  # CommonTeamRoster
            return roster_df.to_dict('records')
        except Exception as e:
            return None
    
    def _rate_limit(self):
        """Simple rate limiting."""
        import time
        time.sleep(0.6)  # 600ms delay
    
    def _find_player_in_rosters(self, player: Player, rosters: Dict[int, List[Dict]]) -> Optional[int]:
        """Find player in NBA API rosters by matching name."""
        # Try to match player name (handle variations)
        player_name_lower = player.name.lower().strip()
        
        # Split name into parts for better matching
        player_parts = player_name_lower.split()
        
        best_match = None
        best_match_score = 0
        
        for team_id, roster in rosters.items():
            for roster_player in roster:
                roster_name = roster_player.get('PLAYER', '').lower().strip()
                
                if not roster_name:
                    continue
                
                # Exact match (highest priority)
                if player_name_lower == roster_name:
                    return team_id
                
                # Check if all name parts match
                roster_parts = roster_name.split()
                if len(player_parts) >= 2 and len(roster_parts) >= 2:
                    # Check if last name matches (most reliable)
                    if player_parts[-1] == roster_parts[-1]:
                        # Check if first name also matches
                        if player_parts[0] == roster_parts[0]:
                            return team_id
                        # Or if first initial matches
                        elif len(player_parts[0]) > 0 and len(roster_parts[0]) > 0:
                            if player_parts[0][0] == roster_parts[0][0]:
                                # Last name + first initial match is good
                                if len(player_parts) == len(roster_parts):
                                    best_match = team_id
                                    best_match_score = 0.8
        
        # Return best match if we found one with high confidence
        if best_match_score >= 0.8:
            return best_match
        
        return None
    
    def sync_player(self, player_id: int, days_back: int = 30) -> bool:
        """
        Sync a specific player's team assignment.
        
        Args:
            player_id: Player ID to sync
            days_back: Number of days to look back
        
        Returns:
            True if updated, False otherwise
        """
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        if not player:
            return False
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Get most recent game stat
        most_recent_stat = self.db.query(PlayerGameStat).join(Game).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.game_date >= cutoff_date,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).order_by(desc(Game.game_date)).first()
        
        if most_recent_stat and player.current_team_id != most_recent_stat.team_id:
            player.current_team_id = most_recent_stat.team_id
            self.db.commit()
            return True
        
        return False
    
    def find_team_mismatches(self, days_back: int = 7) -> List[Dict]:
        """
        Find players whose current_team_id doesn't match their recent game stats.
        
        Args:
            days_back: Number of days to look back
        
        Returns:
            List of mismatch dictionaries
        """
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Get players with recent game stats
        recent_stats = self.db.query(
            PlayerGameStat.player_id,
            PlayerGameStat.team_id,
            func.max(Game.game_date).label('most_recent_date')
        ).join(Game).filter(
            and_(
                Game.game_date >= cutoff_date,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 0
            )
        ).group_by(PlayerGameStat.player_id, PlayerGameStat.team_id).all()
        
        mismatches = []
        
        for stat in recent_stats:
            player = self.db.query(Player).filter(Player.player_id == stat.player_id).first()
            if not player:
                continue
            
            # Get the most recent team for this player
            most_recent = self.db.query(PlayerGameStat).join(Game).filter(
                and_(
                    PlayerGameStat.player_id == stat.player_id,
                    Game.game_date >= cutoff_date,
                    Game.game_status == 'finished',
                    PlayerGameStat.minutes_played > 0
                )
            ).order_by(desc(Game.game_date)).first()
            
            if most_recent and player.current_team_id != most_recent.team_id:
                current_team = self.db.query(Team).filter(Team.team_id == player.current_team_id).first() if player.current_team_id else None
                actual_team = self.db.query(Team).filter(Team.team_id == most_recent.team_id).first()
                
                mismatches.append({
                    'player_id': player.player_id,
                    'player_name': player.name,
                    'current_team': current_team.abbreviation if current_team else None,
                    'actual_team': actual_team.abbreviation if actual_team else None,
                    'most_recent_game': most_recent.game_id
                })
        
        return mismatches

