"""
Lineup Scraper

Scrapes starting lineup confirmations from various sources.
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from app.services.lineup_service import LineupService
from app.models.lineup import Lineup
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.database import SessionLocal


class LineupScraper:
    """Scrape lineup confirmations from various sources."""
    
    def __init__(self, db_session=None, delay: float = 1.0):
        if db_session:
            self.db = db_session
            self.lineup_service = LineupService(db_session)
        else:
            self.db = SessionLocal()
            self.lineup_service = LineupService(self.db)
        
        self.delay = delay
        self.last_request_time = 0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        
        self.last_request_time = time.time()
    
    def _find_player_by_name(self, player_name: str, team_id: Optional[int] = None, update_team: bool = True) -> Optional[Player]:
        """
        Find a player by name, optionally filtering by team.
        If player is found on a different team, optionally update their team assignment.
        
        Args:
            player_name: Player name to search for
            team_id: Expected team ID (optional)
            update_team: If True, update player's team_id if found on different team
        
        Returns:
            Player object or None
        """
        # First, try exact match on expected team
        if team_id:
            query = self.db.query(Player).filter(
                Player.name.ilike(player_name),
                Player.current_team_id == team_id
            )
            player = query.first()
            if player:
                return player
        
        # Try partial match (last name) on expected team
        name_parts = player_name.strip().split()
        if len(name_parts) > 1 and team_id:
            last_name = name_parts[-1]
            query = self.db.query(Player).filter(
                Player.name.ilike(f'%{last_name}%'),
                Player.current_team_id == team_id
            )
            players = query.all()
            if len(players) == 1:
                return players[0]
            elif len(players) > 1:
                # Try to match by first name
                first_name = name_parts[0]
                for p in players:
                    if p.name.startswith(first_name):
                        return p
                return players[0]
        
        # If not found on expected team, search ALL teams (player may have been traded)
        query = self.db.query(Player).filter(Player.name.ilike(player_name))
        player = query.first()
        
        if player:
            # Found player on different team - update if requested
            if update_team and team_id and player.current_team_id != team_id:
                print(f"  ⚠️  Found {player.name} on different team (was {player.current_team_id}, updating to {team_id})")
                player.current_team_id = team_id
                self.db.commit()
            return player
        
        # Try last name match across all teams
        if len(name_parts) > 1:
            last_name = name_parts[-1]
            query = self.db.query(Player).filter(Player.name.ilike(f'%{last_name}%'))
            players = query.all()
            
            if len(players) == 1:
                player = players[0]
                # Update team if requested
                if update_team and team_id and player.current_team_id != team_id:
                    print(f"  ⚠️  Found {player.name} on different team (was {player.current_team_id}, updating to {team_id})")
                    player.current_team_id = team_id
                    self.db.commit()
                return player
            elif len(players) > 1:
                # Try to match by first name
                first_name = name_parts[0]
                for p in players:
                    if p.name.startswith(first_name):
                        # Update team if requested
                        if update_team and team_id and p.current_team_id != team_id:
                            print(f"  ⚠️  Found {p.name} on different team (was {p.current_team_id}, updating to {team_id})")
                            p.current_team_id = team_id
                            self.db.commit()
                        return p
                # Return first match and update team
                player = players[0]
                if update_team and team_id and player.current_team_id != team_id:
                    print(f"  ⚠️  Found {player.name} on different team (was {player.current_team_id}, updating to {team_id})")
                    player.current_team_id = team_id
                    self.db.commit()
                return player
        
        return None
    
    def scrape_nba_com(self, game_date: Optional[date] = None) -> List[Dict]:
        """
        Scrape lineup data from NBA.com.
        
        TODO: Implement actual scraping logic.
        For now, returns empty list.
        
        Returns:
            List of lineup dictionaries
        """
        # Placeholder for NBA.com scraping
        # This would use requests/BeautifulSoup to scrape NBA.com lineup confirmations
        return []
    
    def scrape_espn(self, game_date: Optional[date] = None) -> List[Dict]:
        """
        Scrape lineup data from ESPN for a specific date.
        
        Args:
            game_date: Date to scrape lineups for (if None, uses today)
        
        Returns:
            List of lineup dictionaries with game_id, team_id, starter_player_ids
        """
        self._rate_limit()
        
        if game_date is None:
            game_date = date.today()
        
        try:
            # ESPN NBA scoreboard URL (shows games and lineups)
            # Format: https://www.espn.com/nba/scoreboard/_/date/YYYYMMDD
            date_str = game_date.strftime('%Y%m%d')
            url = f"https://www.espn.com/nba/scoreboard/_/date/{date_str}"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            lineups = []
            
            # Get all games for this date first
            games_for_date = self.db.query(Game).filter(Game.game_date == game_date).all()
            
            if not games_for_date:
                return []
            
            # Build list of boxscore URLs from scoreboard ONCE (usually in game order)
            all_boxscore_links = soup.find_all('a', href=re.compile(r'/nba/boxscore/.*gameId/'))
            all_game_links = soup.find_all('a', href=re.compile(r'/nba/game/.*gameId/'))
            
            boxscore_urls = []
            for link in all_boxscore_links:
                href = link.get('href')
                if not href.startswith('http'):
                    href = f"https://www.espn.com{href}"
                boxscore_urls.append(href)
            
            # Convert game links to boxscore and add
            for link in all_game_links:
                href = link.get('href')
                if '/nba/game/' in href:
                    href = href.replace('/nba/game/', '/nba/boxscore/')
                    if not href.startswith('http'):
                        href = f"https://www.espn.com{href}"
                    if href not in boxscore_urls:
                        boxscore_urls.append(href)
            
            # For each game, use corresponding boxscore URL (assume order matches)
            for game_idx, game in enumerate(games_for_date):
                if game_idx >= len(boxscore_urls):
                    break  # No more boxscore URLs
                
                home_team = self.db.query(Team).filter(Team.team_id == game.home_team_id).first()
                away_team = self.db.query(Team).filter(Team.team_id == game.away_team_id).first()
                
                if not home_team or not away_team:
                    continue
                
                boxscore_url = boxscore_urls[game_idx]
                
                # Navigate to boxscore page to find lineups
                try:
                    self._rate_limit()
                    game_response = requests.get(boxscore_url, headers=self.headers, timeout=15)
                    game_response.raise_for_status()
                    game_soup = BeautifulSoup(game_response.content, 'html.parser')
                    
                    # Look for starting lineup tables on boxscore page
                    # ESPN boxscore has tables with 'STARTER' or 'STARTING' in the text
                    all_tables = game_soup.find_all('table')
                    
                    team_lineups_found = {home_team.team_id: [], away_team.team_id: []}
                    
                    for table in all_tables:
                        # Check if this is a starters table
                        header_text = table.get_text().upper()
                        if 'STARTER' not in header_text and 'STARTING' not in header_text:
                            continue
                        
                        # Extract player names from table rows
                        rows = table.find_all('tr')
                        starters = []
                        
                        for row in rows:
                            player_link = row.find('a', href=re.compile(r'/player/'))
                            if player_link:
                                player_name = player_link.get_text(strip=True)
                                # Clean up name (remove duplicate like "Paul GeorgeP. George" or "Cedric CowardC.")
                                # ESPN format is often "FirstName LastNameNickname" or "FirstName LastNameF. LastName"
                                # Also handles cases like "Cedric CowardC." where there's a trailing initial
                                
                                # Remove trailing single letter/initial (e.g., "CowardC." -> "Coward")
                                if player_name and player_name[-2:][0].isupper() and player_name[-1] == '.':
                                    player_name = player_name[:-2].strip()
                                
                                # If name is too long or has duplicate pattern
                                if len(player_name) > 20:
                                    parts = player_name.split()
                                    if len(parts) >= 2:
                                        # Take first two words as full name
                                        player_name = f'{parts[0]} {parts[1]}'
                                
                                # Remove any remaining trailing initials/duplicates
                                if '.' in player_name and len(player_name.split('.')) > 1:
                                    # Split by period and take the part before first period if it looks like a name
                                    parts = player_name.split('.')
                                    if len(parts[0].split()) >= 2:
                                        player_name = parts[0].strip()
                                
                                starters.append(player_name)
                        
                        if len(starters) >= 5:
                            # Determine which team this is for by checking context
                            # Look for team name near the table
                            table_parent = table.find_parent(['div', 'section'])
                            parent_text = table_parent.get_text() if table_parent else ''
                            
                            # Try to match team
                            if home_team.name.split()[-1].lower() in parent_text.lower() or \
                               (home_team.abbreviation and home_team.abbreviation.lower() in parent_text.lower()):
                                team_lineups_found[home_team.team_id] = starters[:5]
                            elif away_team.name.split()[-1].lower() in parent_text.lower() or \
                                 (away_team.abbreviation and away_team.abbreviation.lower() in parent_text.lower()):
                                team_lineups_found[away_team.team_id] = starters[:5]
                            else:
                                # If we can't determine, try both teams
                                # Usually first table is away team, second is home
                                if not team_lineups_found[away_team.team_id]:
                                    team_lineups_found[away_team.team_id] = starters[:5]
                                elif not team_lineups_found[home_team.team_id]:
                                    team_lineups_found[home_team.team_id] = starters[:5]
                    
                    # Process found lineups
                    for team_id, starter_names in team_lineups_found.items():
                        if len(starter_names) >= 5:
                            # Find player IDs - try to match at least 5 players
                            starter_ids = []
                            matched_names = []
                            for name in starter_names:
                                player = self._find_player_by_name(name, team_id)
                                if player:
                                    starter_ids.append(player.player_id)
                                    matched_names.append(name)
                            
                            # Save lineup if we found at least 3 starters (don't pad with duplicates)
                            if len(starter_ids) >= 3:
                                lineups.append({
                                    'game_id': game.game_id,
                                    'team_id': team_id,
                                    'starter_player_ids': starter_ids[:5],  # Take up to 5, no padding
                                    'source': 'espn'
                                })
                
                except Exception as e:
                    # Continue to next game if this one fails
                    continue
            
            return lineups
            
        except Exception as e:
            print(f"Error scraping ESPN lineups: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def scrape_rotowire(self, game_date: Optional[date] = None) -> List[Dict]:
        """
        Scrape lineup data from Rotowire for a specific date.
        
        Args:
            game_date: Date to scrape lineups for (if None, uses today)
        
        Returns:
            List of lineup dictionaries with game_id, team_id, starter_player_ids
        """
        self._rate_limit()
        
        if game_date is None:
            game_date = date.today()
        
        try:
            # Rotowire NBA lineups URL
            # Main lineups page (may need to filter by date on page)
            # Try multiple possible Rotowire URLs
            # The lineups might be on a different path or require authentication
            # For now, we'll skip Rotowire lineups and rely on ESPN and box score inference
            # TODO: Find correct Rotowire lineup URL or use their API if available
            url = "https://www.rotowire.com/basketball/daily-lineups.php"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            lineups = []
            
            # Find lineup sections (usually organized by game)
            lineup_sections = soup.find_all(['div', 'section'], class_=re.compile(r'lineup|game|matchup', re.I))
            
            for section in lineup_sections:
                # Extract team names
                team_elems = section.find_all(['h3', 'h4', 'div'], class_=re.compile(r'team|name', re.I))
                if len(team_elems) < 2:
                    continue
                
                away_team_text = team_elems[0].get_text(strip=True)
                home_team_text = team_elems[1].get_text(strip=True)
                
                # Find teams
                away_team = self.db.query(Team).filter(
                    Team.abbreviation.ilike(f'%{away_team_text[:3]}%')
                ).first()
                home_team = self.db.query(Team).filter(
                    Team.abbreviation.ilike(f'%{home_team_text[:3]}%')
                ).first()
                
                if not away_team or not home_team:
                    continue
                
                # Find game
                game = self.db.query(Game).filter(
                    Game.game_date == game_date,
                    Game.home_team_id == home_team.team_id,
                    Game.away_team_id == away_team.team_id
                ).first()
                
                if not game:
                    continue
                
                # Extract starters for each team
                starter_lists = section.find_all(['ul', 'div'], class_=re.compile(r'starter|lineup', re.I))
                
                for idx, starter_list in enumerate(starter_lists[:2]):  # Away and home
                    player_links = starter_list.find_all('a', href=re.compile(r'/player/'))
                    if len(player_links) >= 5:
                        starter_names = [link.get_text(strip=True) for link in player_links[:5]]
                        team_id = away_team.team_id if idx == 0 else home_team.team_id
                        
                        # Find player IDs
                        starter_ids = []
                        for name in starter_names:
                            player = self._find_player_by_name(name, team_id)
                            if player:
                                starter_ids.append(player.player_id)
                        
                        if len(starter_ids) == 5:
                            lineups.append({
                                'game_id': game.game_id,
                                'team_id': team_id,
                                'starter_player_ids': starter_ids,
                                'source': 'rotowire'
                            })
            
            return lineups
            
        except Exception as e:
            print(f"Error scraping Rotowire lineups: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def collect_lineups_for_date(self, game_date: date) -> Dict[str, int]:
        """
        Collect lineups for all games on a given date.
        
        For finished games, infers lineups from box scores.
        For upcoming games, attempts to scrape from external sources.
        
        Returns:
            Dict with counts of lineups collected from each source
        """
        from app.models.game import Game
        from sqlalchemy import and_, or_
        
        results = {
            "nba_com": 0,
            "espn": 0,
            "rotowire": 0,
            "inferred": 0,
            "total": 0
        }
        
        # Get all games for this date
        games = self.db.query(Game).filter(
            Game.game_date == game_date
        ).all()
        
        # For finished games, infer lineups from box scores
        finished_games = [g for g in games if g.game_status == 'finished']
        for game in finished_games:
            try:
                inferred = self.lineup_service.infer_lineup_from_game_stats(game.game_id)
                # Save inferred lineups to database
                for team_id, lineup_list in inferred.items():
                    for lineup in lineup_list:
                        # Check if lineup already exists
                        existing = self.db.query(Lineup).filter(
                            and_(
                                Lineup.game_id == game.game_id,
                                Lineup.team_id == team_id,
                                Lineup.player_id == lineup.player_id
                            )
                        ).first()
                        if not existing:
                            self.db.add(lineup)
                    if lineup_list:
                        results["inferred"] += len(lineup_list)
                self.db.commit()
            except Exception as e:
                print(f"Error inferring lineup for game {game.game_id}: {e}")
                self.db.rollback()
        
        # For scheduled/in-progress games, try scraping
        # Also include finished games that might have lineups we can infer
        upcoming_games = [g for g in games if g.game_status in ['scheduled', 'in_progress']]
        finished_games_for_inference = [g for g in games if g.game_status == 'finished']
        if upcoming_games:
            # Scrape from NBA.com
            try:
                nba_lineups = self.scrape_nba_com(game_date)
                for lineup_data in nba_lineups:
                    self._process_lineup_data(lineup_data)
                    results["nba_com"] += 1
            except Exception as e:
                print(f"Error scraping NBA.com: {e}")
            
            # Scrape from ESPN
            try:
                espn_lineups = self.scrape_espn(game_date)
                for lineup_data in espn_lineups:
                    self._process_lineup_data(lineup_data)
                    results["espn"] += 1
            except Exception as e:
                print(f"Error scraping ESPN: {e}")
            
            # Scrape from Rotowire
            try:
                rotowire_lineups = self.scrape_rotowire(game_date)
                for lineup_data in rotowire_lineups:
                    self._process_lineup_data(lineup_data)
                    results["rotowire"] += 1
            except Exception as e:
                print(f"Error scraping Rotowire: {e}")
        
        results["total"] = results["nba_com"] + results["espn"] + results["rotowire"] + results["inferred"]
        
        return results
    
    def _process_lineup_data(self, lineup_data: Dict):
        """
        Process and store lineup data.
        
        Args:
            lineup_data: Dict with lineup information
                - game_id
                - team_id
                - starter_player_ids (list of 3-5 player IDs)
                - bench_player_ids (optional list of bench player IDs)
                - positions (optional list of positions)
        """
        try:
            game_id = lineup_data.get('game_id')
            team_id = lineup_data.get('team_id')
            starter_ids = lineup_data.get('starter_player_ids', [])
            bench_ids = lineup_data.get('bench_player_ids', [])
            positions = lineup_data.get('positions')
            
            if not game_id or not team_id or len(starter_ids) < 3:
                return  # Invalid lineup data (need at least 3 starters)
            
            # Confirm lineup using lineup service
            self.lineup_service.confirm_lineup(
                game_id=game_id,
                team_id=team_id,
                starter_player_ids=starter_ids,
                positions=positions,
                bench_player_ids=bench_ids if bench_ids else None
            )
            
            self.db.commit()
            
        except Exception as e:
            print(f"Error processing lineup data: {e}")
            self.db.rollback()
            # Don't raise - continue processing other lineups
    
    def close(self):
        """Close database session if we created it."""
        if hasattr(self, 'db') and self.db:
            self.db.close()

