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
            
            # Get all games for this date first (filter by sport if available)
            games_for_date = self.db.query(Game).filter(Game.game_date == game_date).all()
            # Filter to only NBA games for ESPN scraping (NFL would use different source)
            games_for_date = [g for g in games_for_date if g.sport == 'NBA']
            
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
            
            # Match games to boxscore URLs by team names (more reliable than index order)
            # ESPN might list games in different order than our database
            for game in games_for_date:
                home_team = self.db.query(Team).filter(Team.team_id == game.home_team_id).first()
                away_team = self.db.query(Team).filter(Team.team_id == game.away_team_id).first()
                
                if not home_team or not away_team:
                    continue
                
                # Find matching boxscore URL
                # We'll try all boxscore URLs and validate each page to find the correct one
                # This is more reliable than trying to match from link context alone
                boxscore_url = None
                potential_urls = []
                
                # Collect all potential boxscore URLs
                for link in all_boxscore_links + all_game_links:
                    href = link.get('href')
                    if '/nba/game/' in href:
                        href = href.replace('/nba/game/', '/nba/boxscore/')
                    if not href.startswith('http'):
                        href = f"https://www.espn.com{href}"
                    if href not in potential_urls:
                        potential_urls.append(href)
                
                # Try each potential URL and validate the page matches our game
                for candidate_url in potential_urls:
                    try:
                        self._rate_limit()
                        test_response = requests.get(candidate_url, headers=self.headers, timeout=10)
                        test_response.raise_for_status()
                        test_soup = BeautifulSoup(test_response.content, 'html.parser')
                        
                        # Validate page title contains both teams
                        page_title = test_soup.find('title')
                        page_title_text = page_title.get_text() if page_title else ''
                        
                        # Build team name variations
                        home_team_names = [home_team.name.split()[-1].lower()]
                        away_team_names = [away_team.name.split()[-1].lower()]
                        if home_team.abbreviation:
                            home_team_names.append(home_team.abbreviation.lower())
                        if away_team.abbreviation:
                            away_team_names.append(away_team.abbreviation.lower())
                        
                        page_text_lower = page_title_text.lower()
                        home_found = any(name in page_text_lower for name in home_team_names)
                        away_found = any(name in page_text_lower for name in away_team_names)
                        
                        # If BOTH teams are in the title, this is our game!
                        if home_found and away_found:
                            boxscore_url = candidate_url
                            break  # Found the correct game
                    except:
                        continue  # Try next URL if this one fails
                
                # If still no match found, skip this game
                if not boxscore_url:
                    print(f"  ⚠️  Could not find matching boxscore for game {game.game_id} ({away_team.abbreviation} @ {home_team.abbreviation})")
                    print(f"     Checked {len(potential_urls)} boxscore pages, none matched both teams. Skipping.")
                    continue  # Skip this game
                
                # Navigate to boxscore page to find lineups
                # Note: We already validated this page matches our game when finding the URL
                try:
                    self._rate_limit()
                    game_response = requests.get(boxscore_url, headers=self.headers, timeout=15)
                    game_response.raise_for_status()
                    game_soup = BeautifulSoup(game_response.content, 'html.parser')
                    
                    # Look for starting lineup data in multiple ways
                    # ESPN boxscore may have lineups in tables, divs, or JSON data
                    team_lineups_found = {home_team.team_id: [], away_team.team_id: []}
                    
                    # Method 1: Look for starting lineup tables
                    all_tables = game_soup.find_all('table')
                    
                    for table in all_tables:
                        # Check if this is a starters table
                        header_text = table.get_text().upper()
                        if 'STARTER' not in header_text and 'STARTING' not in header_text:
                            continue
                        
                        # Extract player names from table rows
                        # ESPN tables often have starters first (5 players), then bench
                        # Look for "STARTER" header row first to find where starters begin
                        rows = table.find_all('tr')
                        starters = []
                        found_starter_header = False
                        
                        for row in rows:
                            row_text = row.get_text().upper()
                            # Check if this is the "STARTER" header row
                            if 'STARTER' in row_text or 'STARTING' in row_text:
                                found_starter_header = True
                                continue  # Skip header row
                            
                            # Only extract players after finding the starter header
                            # Stop after getting 5 starters (ESPN usually lists starters, then bench)
                            if len(starters) >= 5:
                                break
                            
                            player_link = row.find('a', href=re.compile(r'/player/'))
                            if player_link:
                                player_name = player_link.get_text(strip=True)
                                # Clean up name (remove duplicate like "Anthony DavisA. Davis")
                                player_name = self._clean_player_name(player_name)
                                if player_name:
                                    starters.append(player_name)
                        
                        # If we didn't find a starter header but have rows with players,
                        # assume first 5 are starters (common ESPN format)
                        if not found_starter_header and len(starters) == 0:
                            for row in rows[:10]:  # Check first 10 rows
                                if len(starters) >= 5:
                                    break
                                player_link = row.find('a', href=re.compile(r'/player/'))
                                if player_link:
                                    player_name = self._clean_player_name(player_link.get_text(strip=True))
                                    if player_name:
                                        starters.append(player_name)
                        
                        if len(starters) >= 5:
                            # Determine which team this is for by checking context
                            # Look at table parent, table headers, and nearby text
                            table_parent = table.find_parent(['div', 'section', 'article'])
                            parent_text = table_parent.get_text() if table_parent else ''
                            
                            # Also check the table itself for team clues
                            table_headers = table.find_all(['th', 'thead'])
                            for header in table_headers:
                                header_text = header.get_text()
                                parent_text += " " + header_text
                            
                            # Check for team name in table caption or nearby elements
                            caption = table.find('caption')
                            if caption:
                                parent_text += " " + caption.get_text()
                            
                            # Also check sibling elements for team names
                            if table_parent:
                                siblings = table_parent.find_all(['h2', 'h3', 'h4', 'div'], class_=re.compile(r'team|name', re.I))
                                for sibling in siblings[:3]:
                                    parent_text += " " + sibling.get_text()
                            
                            self._assign_lineup_to_team(team_lineups_found, starters[:5], home_team, away_team, parent_text)
                    
                    # Method 2: Look for lineup data in divs with class names containing 'lineup', 'starter', etc.
                    lineup_divs = game_soup.find_all(['div', 'section'], class_=re.compile(r'lineup|starter|starting', re.I))
                    
                    for div in lineup_divs:
                        player_links = div.find_all('a', href=re.compile(r'/player/'))
                        if len(player_links) >= 5:
                            starters = []
                            for link in player_links[:5]:
                                player_name = self._clean_player_name(link.get_text(strip=True))
                                if player_name:
                                    starters.append(player_name)
                            
                            if len(starters) >= 5:
                                parent_text = div.get_text()
                                self._assign_lineup_to_team(team_lineups_found, starters[:5], home_team, away_team, parent_text)
                    
                    # Method 3: Look for JSON data in script tags (ESPN sometimes embeds lineup data here)
                    script_tags = game_soup.find_all('script', type='application/json')
                    for script in script_tags:
                        try:
                            import json
                            data = json.loads(script.string)
                            # Recursively search for lineup data in JSON
                            lineup_data = self._extract_lineup_from_json(data, home_team, away_team)
                            if lineup_data:
                                for team_id, starter_names in lineup_data.items():
                                    if len(starter_names) >= 5 and not team_lineups_found.get(team_id):
                                        team_lineups_found[team_id] = starter_names[:5]
                        except:
                            continue
                    
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
        
        Note: Rotowire lineup URL currently returns 404. This method returns empty list silently.
        TODO: Find correct Rotowire lineup URL or use their API if available.
        """
        # Rotowire lineup URL is currently unavailable (returns 404)
        # Skip silently to avoid noise - ESPN is the primary source anyway
        # When Rotowire URL is fixed, uncomment the code below
        return []
        
        # DISABLED CODE - Uncomment when Rotowire URL is fixed
        # self._rate_limit()
        # 
        # if game_date is None:
        #     game_date = date.today()
        # 
        # try:
        #     url = "https://www.rotowire.com/basketball/daily-lineups.php"
        #     response = requests.get(url, headers=self.headers, timeout=15)
        #     response.raise_for_status()
        #     # ... rest of scraping logic ...
        # except Exception as e:
        #     # Log warning but don't print traceback (avoid noise)
        #     print(f"⚠️  Rotowire lineup scraping unavailable: {e}")
        #     return []
    
    def collect_lineups_for_date(self, game_date: date, sport: Optional[str] = None) -> Dict[str, int]:
        """
        Collect lineups for all games on a given date.
        
        For finished games, infers lineups from box scores.
        For upcoming games, attempts to scrape from external sources.
        
        Args:
            game_date: Date to collect lineups for
            sport: Optional sport filter ('NBA' or 'NFL'). If None, collects for all sports.
        
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
        
        # Get games for this date, filtered by sport if provided
        query = self.db.query(Game).filter(Game.game_date == game_date)
        if sport:
            query = query.filter(Game.sport == sport)
        games = query.all()
        
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
        # Only scrape NBA.com for NBA games
        upcoming_games = [g for g in games if g.game_status in ['scheduled', 'in_progress']]
        if upcoming_games:
            # Only scrape NBA.com if sport is NBA (or not specified for backward compatibility)
            if not sport or sport == 'NBA':
                try:
                    nba_lineups = self.scrape_nba_com(game_date)
                    for lineup_data in nba_lineups:
                        self._process_lineup_data(lineup_data)
                        results["nba_com"] += 1
                except Exception as e:
                    print(f"Error scraping NBA.com: {e}")
            
            # Scrape from ESPN (works for both NBA and NFL)
            try:
                espn_lineups = self.scrape_espn(game_date)
                for lineup_data in espn_lineups:
                    self._process_lineup_data(lineup_data)
                    results["espn"] += 1
            except Exception as e:
                print(f"Error scraping ESPN: {e}")
            
            # Scrape from Rotowire (currently disabled - URL returns 404)
            try:
                rotowire_lineups = self.scrape_rotowire(game_date)
                for lineup_data in rotowire_lineups:
                    self._process_lineup_data(lineup_data)
                    results["rotowire"] += 1
            except Exception as e:
                # Silently skip - Rotowire is not currently available
                pass
        
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
            
            # Verify game exists and team_id matches the game
            from app.models.game import Game
            game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                print(f"  ⚠️  Warning: Game {game_id} not found, skipping lineup")
                return
            
            if game.home_team_id != team_id and game.away_team_id != team_id:
                print(f"  ⚠️  Warning: Team {team_id} not in game {game_id}, skipping lineup")
                return
            
            # Update player teams based on lineup data (ensure players are on correct teams)
            # This is important because players may have been traded or team assignments may be stale
            for player_id in starter_ids + (bench_ids if bench_ids else []):
                player = self.db.query(Player).filter(Player.player_id == player_id).first()
                if player and player.current_team_id != team_id:
                    # Player's team assignment is wrong - update it based on confirmed lineup
                    print(f"  ✅ Updated {player.name} team: {player.current_team_id} → {team_id} (from confirmed lineup)")
                    player.current_team_id = team_id
            
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
    
    def _clean_player_name(self, player_name: str) -> str:
        """Clean up player name from ESPN format (e.g., "Anthony DavisA. Davis" -> "Anthony Davis")."""
        if not player_name:
            return ""
        
        # ESPN format is often "FirstName LastNameNickname" or "FirstName LastNameF. LastName"
        # Example: "Anthony DavisA. Davis" or "Daniel GaffordD. Gafford"
        
        # Pattern: If name has a capital letter followed by a period and space/capital letter
        # at the end, that's likely a duplicate (e.g., "DavisA. Davis" -> "Davis")
        import re
        
        # Try to find and remove duplicate patterns like "LastNameFirstInitial. LastName"
        # Pattern: Last name, followed by first initial and period, followed by same last name
        # Example: "DavisA. Davis" -> "Davis"
        duplicate_pattern = r'([A-Z][a-z]+)([A-Z]\.?\s*\1)'
        match = re.search(duplicate_pattern, player_name)
        if match:
            # Extract just the last name (or full name without duplicate)
            last_name = match.group(1)
            # Find where the last name appears first
            last_name_pos = player_name.find(last_name)
            if last_name_pos > 0:
                # Take everything before the duplicate starts
                player_name = player_name[:last_name_pos + len(last_name)].strip()
        
        # Fallback: If name has a period followed by a space and capitalized word
        # that's likely "FirstName LastNameF. LastName" -> "FirstName LastName"
        if '.' in player_name:
            # Find the last period
            last_period = player_name.rfind('.')
            if last_period > 0:
                # Check if after the period is a space and capitalized word
                after_period = player_name[last_period + 1:].strip()
                if after_period and after_period[0].isupper():
                    # Check if the part before period looks like a name (has space)
                    before_period = player_name[:last_period].strip()
                    if ' ' in before_period and len(before_period.split()) >= 2:
                        # Take the part before the period
                        player_name = before_period
        
        # If name is still too long, take first two words
        if len(player_name) > 25:
            parts = player_name.split()
            if len(parts) >= 2:
                player_name = f'{parts[0]} {parts[1]}'
        
        # Final cleanup: remove any trailing initials/periods
        player_name = player_name.strip()
        # Remove trailing single letter/initial (e.g., "CowardC." -> "Coward")
        if len(player_name) >= 2 and player_name[-2:][0].isupper() and player_name[-1] == '.':
            player_name = player_name[:-2].strip()
        
        return player_name.strip()
    
    def _assign_lineup_to_team(self, team_lineups_found: dict, starters: list, home_team, away_team, context_text: str):
        """Assign lineup to the correct team based on context."""
        context_lower = context_text.lower()
        
        # Try to match team by name or abbreviation
        if home_team.name.split()[-1].lower() in context_lower or \
           (home_team.abbreviation and home_team.abbreviation.lower() in context_lower):
            if not team_lineups_found[home_team.team_id]:  # Don't overwrite existing
                team_lineups_found[home_team.team_id] = starters
        elif away_team.name.split()[-1].lower() in context_lower or \
             (away_team.abbreviation and away_team.abbreviation.lower() in context_lower):
            if not team_lineups_found[away_team.team_id]:  # Don't overwrite existing
                team_lineups_found[away_team.team_id] = starters
        else:
            # If we can't determine, assign based on order
            # Usually first table is away team, second is home
            if not team_lineups_found[away_team.team_id]:
                team_lineups_found[away_team.team_id] = starters
            elif not team_lineups_found[home_team.team_id]:
                team_lineups_found[home_team.team_id] = starters
    
    def _extract_lineup_from_json(self, data: any, home_team, away_team: Team) -> Optional[Dict[int, List[str]]]:
        """Recursively extract lineup data from JSON structure."""
        result = {}
        
        if isinstance(data, dict):
            # Look for keys that might contain lineup data
            for key, value in data.items():
                if 'lineup' in key.lower() or 'starter' in key.lower() or 'starting' in key.lower():
                    if isinstance(value, (list, dict)):
                        # Try to extract player names
                        players = []
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    name = item.get('name') or item.get('playerName') or item.get('displayName')
                                    if name:
                                        players.append(self._clean_player_name(name))
                        elif isinstance(value, dict):
                            # Could be organized by team
                            for team_key, team_data in value.items():
                                if isinstance(team_data, list):
                                    team_players = []
                                    for item in team_data:
                                        if isinstance(item, dict):
                                            name = item.get('name') or item.get('playerName') or item.get('displayName')
                                            if name:
                                                team_players.append(self._clean_player_name(name))
                                    if len(team_players) >= 5:
                                        # Try to match team
                                        if home_team.name.split()[-1].lower() in team_key.lower() or \
                                           (home_team.abbreviation and home_team.abbreviation.lower() in team_key.lower()):
                                            result[home_team.team_id] = team_players[:5]
                                        elif away_team.name.split()[-1].lower() in team_key.lower() or \
                                             (away_team.abbreviation and away_team.abbreviation.lower() in team_key.lower()):
                                            result[away_team.team_id] = team_players[:5]
                
                # Recursively search nested structures
                nested = self._extract_lineup_from_json(value, home_team, away_team)
                if nested:
                    result.update(nested)
        
        elif isinstance(data, list):
            for item in data:
                nested = self._extract_lineup_from_json(item, home_team, away_team)
                if nested:
                    result.update(nested)
        
        return result if result else None
    
    def close(self):
        """Close database session if we created it."""
        if hasattr(self, 'db') and self.db:
            self.db.close()

