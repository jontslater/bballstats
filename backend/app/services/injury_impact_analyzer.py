"""
Injury Impact Analyzer

Analyzes historical patterns of how injuries affect player minutes and stats.
"""
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import date, timedelta
from app.models.injury_impact_history import InjuryImpactHistory
from app.models.player_game_stat import PlayerGameStat
from app.models.player import Player
from app.models.game import Game
from app.models.injury import Injury


class InjuryImpactAnalyzer:
    """Analyze how injuries affect player minutes and stats."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def analyze_historical_impacts(self, min_games: int = 3) -> Dict[str, int]:
        """
        Analyze all historical injury impacts.
        
        This looks at games where a player was injured and calculates
        how much backup players' minutes/stats increased.
        
        Args:
            min_games: Minimum games required to calculate impact
        
        Returns:
            Dict with counts of impacts analyzed
        """
        # Get all injuries that resulted in missed games
        injuries = self.db.query(Injury).filter(
            and_(
                Injury.status.in_(['Out', 'Doubtful']),
                Injury.actual_return_date.isnot(None)  # Has returned, so we can analyze
            )
        ).all()
        
        analyzed = 0
        created = 0
        
        for injury in injuries:
            # Find backup players (same position, same team)
            injured_player = self.db.query(Player).filter(
                Player.player_id == injury.player_id
            ).first()
            
            if not injured_player or not injured_player.position:
                continue
            
            # Get games the player missed
            missed_games = self._get_missed_games(
                player_id=injury.player_id,
                team_id=injured_player.current_team_id,
                injury_date=injury.injury_date,
                return_date=injury.actual_return_date
            )
            
            if len(missed_games) < min_games:
                continue
            
            backups = self._find_backup_players(
                team_id=injured_player.current_team_id,
                position=injured_player.position,
                exclude_player_id=injury.player_id
            )
            
            # Analyze impact for each backup
            for backup in backups:
                impact = self._calculate_impact(
                    injured_player_id=injury.player_id,
                    beneficiary_player_id=backup.player_id,
                    missed_game_ids=[g.game_id for g in missed_games],
                    injury_date=injury.injury_date
                )
                
                if impact:
                    # Store impact history
                    for game_id, impact_data in impact.items():
                        existing = self.db.query(InjuryImpactHistory).filter(
                            and_(
                                InjuryImpactHistory.injured_player_id == injury.player_id,
                                InjuryImpactHistory.beneficiary_player_id == backup.player_id,
                                InjuryImpactHistory.game_id == game_id
                            )
                        ).first()
                        
                        if not existing:
                            history = InjuryImpactHistory(
                                injured_player_id=injury.player_id,
                                beneficiary_player_id=backup.player_id,
                                game_id=game_id,
                                minutes_increase=impact_data['minutes_increase'],
                                stat_increase_points=impact_data['stat_increase_points'],
                                stat_increase_rebounds=impact_data['stat_increase_rebounds'],
                                stat_increase_assists=impact_data['stat_increase_assists'],
                                position=injured_player.position
                            )
                            self.db.add(history)
                            created += 1
                    
                    analyzed += 1
        
        self.db.commit()
        
        return {
            "injuries_analyzed": analyzed,
            "impact_records_created": created
        }
    
    def _get_missed_games(
        self,
        player_id: int,
        team_id: int,
        injury_date: date,
        return_date: date
    ) -> List[Game]:
        """Get games a player missed due to injury."""
        # Get games where player's team played but player didn't
        team_games = self.db.query(Game).filter(
            and_(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id
                ),
                Game.game_date >= injury_date,
                Game.game_date < return_date,
                Game.game_status == 'finished'
            )
        ).all()
        
        # Filter to games where player didn't play
        missed_games = []
        for game in team_games:
            player_stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.player_id == player_id
                )
            ).first()
            
            if not player_stat or player_stat.minutes_played == 0:
                missed_games.append(game)
        
        return missed_games
    
    def _find_backup_players(
        self,
        team_id: int,
        position: str,
        exclude_player_id: int
    ) -> List[Player]:
        """Find backup players at the same position on the same team."""
        return self.db.query(Player).filter(
            and_(
                Player.current_team_id == team_id,
                Player.position == position,
                Player.player_id != exclude_player_id
            )
        ).all()
    
    def _calculate_impact(
        self,
        injured_player_id: int,
        beneficiary_player_id: int,
        missed_game_ids: List[int],
        injury_date: date
    ) -> Optional[Dict[int, Dict]]:
        """
        Calculate how much a beneficiary player's stats increased
        when the injured player was out.
        
        Returns:
            Dict mapping game_id to impact data, or None if insufficient data
        """
        if not missed_game_ids:
            return None
        
        # Get beneficiary's baseline (games before injury)
        injured_player = self.db.query(Player).filter(
            Player.player_id == injured_player_id
        ).first()
        
        if not injured_player:
            return None
        
        # Get baseline stats (last 10 games before injury)
        baseline_games = self.db.query(Game).join(
            PlayerGameStat, Game.game_id == PlayerGameStat.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == beneficiary_player_id,
                PlayerGameStat.team_id == injured_player.current_team_id,
                Game.game_date < injury_date,
                Game.game_status == 'finished'
            )
        ).order_by(Game.game_date.desc()).limit(10).all()
        
        if not baseline_games:
            return None
        
        baseline_stats = []
        for game in baseline_games:
            stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game.game_id,
                    PlayerGameStat.player_id == beneficiary_player_id
                )
            ).first()
            if stat:
                baseline_stats.append(stat)
        
        if not baseline_stats:
            return None
        
        # Calculate baseline averages
        baseline_minutes = sum(s.minutes_played or 0 for s in baseline_stats) / len(baseline_stats)
        baseline_points = sum(s.points or 0 for s in baseline_stats) / len(baseline_stats)
        baseline_rebounds = sum(s.rebounds or 0 for s in baseline_stats) / len(baseline_stats)
        baseline_assists = sum(s.assists or 0 for s in baseline_stats) / len(baseline_stats)
        
        # Calculate impact for each missed game
        impacts = {}
        for game_id in missed_game_ids:
            stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.game_id == game_id,
                    PlayerGameStat.player_id == beneficiary_player_id
                )
            ).first()
            
            if stat:
                impacts[game_id] = {
                    'minutes_increase': max(0, int(stat.minutes_played - baseline_minutes)),
                    'stat_increase_points': round(stat.points - baseline_points, 2),
                    'stat_increase_rebounds': round(stat.rebounds - baseline_rebounds, 2),
                    'stat_increase_assists': round(stat.assists - baseline_assists, 2)
                }
        
        return impacts if impacts else None
    
    def get_expected_impact(
        self,
        injured_player_id: int,
        beneficiary_player_id: int
    ) -> Optional[Dict]:
        """
        Get expected impact for a beneficiary player when an injured player is out.
        
        Returns:
            Dict with expected minutes and stat increases
        """
        # Get historical impacts
        impacts = self.db.query(InjuryImpactHistory).filter(
            and_(
                InjuryImpactHistory.injured_player_id == injured_player_id,
                InjuryImpactHistory.beneficiary_player_id == beneficiary_player_id
            )
        ).all()
        
        if not impacts:
            return None
        
        # Calculate averages
        avg_minutes_increase = sum(i.minutes_increase for i in impacts) / len(impacts)
        avg_points_increase = sum(i.stat_increase_points for i in impacts) / len(impacts)
        avg_rebounds_increase = sum(i.stat_increase_rebounds for i in impacts) / len(impacts)
        avg_assists_increase = sum(i.stat_increase_assists for i in impacts) / len(impacts)
        
        return {
            "games_analyzed": len(impacts),
            "avg_minutes_increase": round(avg_minutes_increase, 1),
            "avg_points_increase": round(avg_points_increase, 2),
            "avg_rebounds_increase": round(avg_rebounds_increase, 2),
            "avg_assists_increase": round(avg_assists_increase, 2)
        }

