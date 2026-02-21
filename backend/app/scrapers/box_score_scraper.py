"""
Box Score Scraper

Scrapes box scores from ESPN and Rotowire as fallback sources.
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from app.database import SessionLocal
from app.models.game import Game
from app.models.player import Player
from app.models.team import Team
from app.models.player_game_stat import PlayerGameStat
from sqlalchemy import func


class BoxScoreScraper:
    """Scrape box scores from ESPN and Rotowire."""
    
    def __init__(self, db_session=None, delay: float = 1.0):
        if db_session:
            self.db = db_session
        else:
            self.db = SessionLocal()
        
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
    
    def _find_player_by_name(self, player_name: str, team_id: Optional[int] = None) -> Optional[Player]:
        """Find a player by name, optionally filtering by team."""
        query = self.db.query(Player).filter(Player.name.ilike(player_name))
        if team_id:
            query = query.filter(Player.current_team_id == team_id)
        
        player = query.first()
        if player:
            return player
        
        # Try partial match (last name)
        name_parts = player_name.strip().split()
        if len(name_parts) > 1:
            last_name = name_parts[-1]
            query = self.db.query(Player).filter(Player.name.ilike(f'%{last_name}%'))
            if team_id:
                query = query.filter(Player.current_team_id == team_id)
            
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
        
        return None
    
    def scrape_espn_box_score(self, game_id: int) -> Optional[Dict]:
        """
        Scrape box score from ESPN for a specific game.
        
        Args:
            game_id: Game ID in our database
        
        Returns:
            Dict with player stats, or None if not found
        """
        self._rate_limit()
        
        try:
            # Get game from database
            game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                return None
            
            home_team = self.db.query(Team).filter(Team.team_id == game.home_team_id).first()
            away_team = self.db.query(Team).filter(Team.team_id == game.away_team_id).first()
            
            if not home_team or not away_team:
                return None
            
            # ESPN box score URL format
            date_str = game.game_date.strftime('%Y%m%d')
            
            # Go to ESPN scoreboard for the date
            scoreboard_url = f"https://www.espn.com/nba/scoreboard/_/date/{date_str}"
            
            response = requests.get(scoreboard_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all boxscore links on the scoreboard page
            # ESPN uses various patterns: /nba/boxscore/_/gameId/, /nba/game/_/gameId/, etc.
            boxscore_links = soup.find_all('a', href=re.compile(r'/nba/(boxscore|game)/'))
            
            # Also look for links with gameId in the URL
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                if '/boxscore/' in href or ('/game/' in href and 'gameId' in href):
                    if href not in [l.get('href') for l in boxscore_links]:
                        boxscore_links.append(link)
            
            # Try each boxscore link and match to our game
            for link in boxscore_links:
                href = link.get('href')
                if not href:
                    continue
                
                # Convert to full URL if needed
                if not href.startswith('http'):
                    href = f"https://www.espn.com{href}"
                
                # Convert /game/ URLs to /boxscore/ URLs
                if '/game/' in href and '/boxscore/' not in href:
                    href = href.replace('/game/', '/boxscore/')
                
                try:
                    self._rate_limit()
                    box_score_response = requests.get(href, headers=self.headers, timeout=15)
                    box_score_response.raise_for_status()
                    
                    box_soup = BeautifulSoup(box_score_response.content, 'html.parser')
                    
                    # Check if this box score matches our game by looking for team names
                    page_text = box_soup.get_text().upper()
                    home_match = home_team.abbreviation.upper() in page_text or home_team.name.upper() in page_text
                    away_match = away_team.abbreviation.upper() in page_text or away_team.name.upper() in page_text
                    
                    if home_match and away_match:
                        # This is our game! Parse the box score
                        result = self._parse_espn_box_score(box_soup, game, home_team, away_team)
                        if result and result.get('player_stats'):
                            return result
                        elif result:
                            print(f"  ⚠️  Box score parsed but no player stats found for {away_team.abbreviation} @ {home_team.abbreviation}")
                
                except Exception as e:
                    # Continue to next link if this one fails
                    print(f"  ⚠️  Error processing box score link: {str(e)[:100]}")
                    continue
            
            print(f"  ❌ Could not find matching box score for {away_team.abbreviation} @ {home_team.abbreviation}")
            return None
            
        except Exception as e:
            print(f"Error scraping ESPN box score for game {game_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_espn_box_score(self, soup: BeautifulSoup, game: Game, home_team: Team, away_team: Team) -> Dict:
        """Parse ESPN box score HTML.
        
        ESPN structure: Player names and stats are in SEPARATE tables.
        - Name tables: One cell per row with player link
        - Stats tables: Multiple columns (MIN, PTS, REB, AST, etc.)
        We need to match them by row index.
        """
        stats = {
            'game_id': game.game_id,
            'player_stats': []
        }
        
        # ESPN box score structure: Look for tables
        tables = soup.find_all('table')
        
        # Track which team we're currently parsing
        # Start with away team (usually first in box scores)
        current_team_id = away_team.team_id
        
        # Find pairs of name/stats tables
        # ESPN typically has: name_table, stats_table, name_table, stats_table (for away, home)
        name_tables = []
        stats_tables = []
        
        for table in tables:
            # Check if this is a name table (has player links, single column)
            player_links = table.find_all('a', href=re.compile(r'/player/'))
            if player_links and len(player_links) > 5:  # Has multiple players
                name_tables.append(table)
            
            # Check if this is a stats table (has MIN/PTS headers)
            table_text = table.get_text()
            if 'MIN' in table_text and 'PTS' in table_text:
                rows = table.find_all('tr')
                # Check if first row has header
                if rows:
                    first_row_cells = [cell.get_text(strip=True).upper() for cell in rows[0].find_all(['td', 'th'])]
                    if 'MIN' in first_row_cells and 'PTS' in first_row_cells:
                        stats_tables.append(table)
        
        # Match name tables with stats tables (they should be in pairs)
        for name_table_idx, name_table in enumerate(name_tables):
            # Find corresponding stats table (usually the next one)
            stats_table = None
            if name_table_idx < len(stats_tables):
                stats_table = stats_tables[name_table_idx]
            elif len(stats_tables) > 0:
                # Fallback: use first stats table
                stats_table = stats_tables[0]
            
            if not stats_table:
                continue
            
            # Determine team for this pair - be more explicit
            name_table_text = name_table.get_text().upper()
            # Check for team indicators more carefully
            # Look for team name/abbreviation in the table or nearby context
            table_parent = name_table.find_parent(['div', 'section', 'article'])
            parent_text = (table_parent.get_text().upper() if table_parent else "") + " " + name_table_text
            
            # Also check the page title and nearby headings for team names
            page_title = soup.find('title')
            title_text = (page_title.get_text().upper() if page_title else "")
            all_context = parent_text + " " + title_text
            
            # Check home team first (more specific)
            home_in_context = (home_team.abbreviation.upper() in all_context or 
                              home_team.name.upper() in all_context or
                              any(word in all_context for word in home_team.name.upper().split() if len(word) > 3))
            away_in_context = (away_team.abbreviation.upper() in all_context or 
                               away_team.name.upper() in all_context or
                               any(word in all_context for word in away_team.name.upper().split() if len(word) > 3))
            
            if home_in_context and not away_in_context:
                current_team_id = home_team.team_id
            elif away_in_context and not home_in_context:
                current_team_id = away_team.team_id
            elif home_in_context and away_in_context:
                # Both teams mentioned - use position in page (first is usually away, second is home)
                if name_table_idx % 2 == 0:
                    current_team_id = away_team.team_id  # First table is usually away
                else:
                    current_team_id = home_team.team_id  # Second table is usually home
            else:
                # Fallback: alternate between teams if we can't determine
                # This is less reliable but better than nothing
                if name_table_idx % 2 == 0:
                    current_team_id = away_team.team_id  # First table is usually away
                else:
                    current_team_id = home_team.team_id  # Second table is usually home
            
            # Get player names from name table
            # IMPORTANT: Skip non-player rows (like "starters", "bench", "team" labels)
            name_rows = name_table.find_all('tr')
            player_names = []
            player_row_indices = []  # Track which name table rows correspond to players
            
            for name_row_idx, name_row in enumerate(name_rows):
                player_link = name_row.find('a', href=re.compile(r'/player/'))
                if player_link:
                    player_name = player_link.get_text(strip=True)
                    # Clean up name (ESPN format: "Dean WadeD. Wade" -> "Dean Wade")
                    # The pattern is usually: "FirstName LastNameInitial. LastName"
                    # We want to extract "FirstName LastName"
                    parts = player_name.split()
                    if len(parts) >= 2:
                        # Check if second part ends with period and has a letter before it (like "WadeD.")
                        if len(parts[1]) > 3 and parts[1][-1] == '.':
                            # Extract last name by removing the initial and period
                            # "WadeD." -> "Wade"
                            last_name = parts[1].rstrip('.').rstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
                            if last_name:
                                player_name = f"{parts[0]} {last_name}"
                            else:
                                # Fallback: use first two words
                                player_name = ' '.join(parts[:2])
                        elif len(parts) >= 3:
                            # Format might be "FirstName LastName Initial. LastName"
                            # Take first two words
                            player_name = f"{parts[0]} {parts[1]}"
                        else:
                            # Just take first two words
                            player_name = ' '.join(parts[:2])
                    player_names.append(player_name)
                    player_row_indices.append(name_row_idx)  # Track this is a player row
            
            # Get stats from stats table
            stats_rows = stats_table.find_all('tr')
            
            # Find header row - be more specific to avoid matching wrong columns
            header_indices = {}
            header_row_idx = None
            for row_idx, row in enumerate(stats_rows):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
                
                # Check if this looks like a header row
                # Must have MIN and PTS, and PTS should be the actual points column (not 3PM, FGM, etc.)
                has_min = 'MIN' in cell_texts
                has_pts = 'PTS' in cell_texts or 'POINTS' in cell_texts
                
                # Make sure we're not confusing PTS with other columns
                # Check that PTS appears before or near other stat columns
                if has_min and has_pts:
                    # Verify this is the real header by checking column order
                    # Typical ESPN order: MIN, FG, FGA, FG%, 3PM, 3PA, 3P%, FT, FTA, FT%, OR, DR, REB, AST, STL, BLK, TO, PF, PTS, +/-
                    # PTS should be near the end, after REB and AST
                    # 3PM comes much earlier, so we can use position to distinguish
                    pts_text = 'PTS' if 'PTS' in cell_texts else 'POINTS'
                    pts_idx = cell_texts.index(pts_text)
                    min_idx = cell_texts.index('MIN')
                    
                    # Verify we have both MIN and PTS, and PTS is a valid column
                    # Note: In ESPN's format, PTS can come before or after 3PT
                    # What matters is that we match "PTS" exactly, not "3PT" or "3PM"
                    # ESPN format: MIN, PTS, FG, 3PT, FT, REB, AST, ... (PTS is at index 1, 3PT is at index 3)
                    if pts_idx >= min_idx:  # PTS should come at or after MIN (usually right after)
                        header_row_idx = row_idx
                        for idx, text in enumerate(cell_texts):
                            # Only map exact matches to avoid confusion
                            # Make sure we're not matching "3PM" or other similar columns
                            text_clean = text.strip()
                            if text_clean == 'MIN':
                                header_indices['MIN'] = idx
                            elif text_clean == 'PTS' or text_clean == 'POINTS':
                                # Double-check: PTS should not be confused with 3PM
                                # 3PM typically appears earlier, PTS appears later
                                header_indices['PTS'] = idx
                            elif text_clean == 'REB' or text_clean == 'REBS':
                                header_indices['REB'] = idx
                            elif text_clean == 'AST' or text_clean == 'ASTS':
                                header_indices['AST'] = idx
                        
                        # Verify we found PTS (not 3PM or something else)
                        if 'PTS' in header_indices:
                            # Additional validation: check that PTS column index is reasonable
                            # PTS should typically be after REB and AST in ESPN's format
                            pts_col_idx = header_indices['PTS']
                            # Log header for debugging (first table only)
                            if name_table_idx == 0:
                                print(f"      📊 Header columns: {cell_texts[:pts_col_idx+3]}")
                                print(f"      📍 PTS column index: {pts_col_idx}, value: '{cell_texts[pts_col_idx] if pts_col_idx < len(cell_texts) else 'N/A'}'")
                            break
            
            if not header_indices or 'PTS' not in header_indices:
                # If we didn't find PTS, try a more lenient search but log a warning
                print(f"      ⚠️  Could not find PTS column in header, trying fallback...")
                for row_idx, row in enumerate(stats_rows):
                    cells = row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
                    if 'MIN' in cell_texts:
                        header_row_idx = row_idx
                        for idx, text in enumerate(cell_texts):
                            # Try to find PTS even if it's not in the expected position
                            if text == 'PTS' or text == 'POINTS':
                                header_indices['PTS'] = idx
                            if text == 'MIN':
                                header_indices['MIN'] = idx
                            if text == 'REB' or text == 'REBS':
                                header_indices['REB'] = idx
                            if text == 'AST' or text == 'ASTS':
                                header_indices['AST'] = idx
                        if 'PTS' in header_indices:
                            break
                
                if 'PTS' not in header_indices:
                    print(f"      ❌ Could not find PTS column, skipping this table")
                    continue
            
            # Match players with stats by row index
            # We need to account for potential second header rows in stats table (for bench section)
            # Strategy: Match first player to first stats row, then continue sequentially
            # But skip any header rows in stats table (rows that have "MIN" and "PTS" as values)
            stats_row_idx = header_row_idx + 1  # Start after first header
            
            for player_idx, player_name in enumerate(player_names):
                # Skip any header rows in stats table
                while stats_row_idx < len(stats_rows):
                    stats_row = stats_rows[stats_row_idx]
                    cells = stats_row.find_all(['td', 'th'])
                    cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
                    
                    # Check if this is a header row (has "MIN" and "PTS" as values, not column headers)
                    if len(cell_texts) > 1 and cell_texts[0] == 'MIN' and cell_texts[1] == 'PTS':
                        # This is a second header row (for bench section), skip it
                        stats_row_idx += 1
                        continue
                    else:
                        # This is a player stats row
                        break
                
                if stats_row_idx >= len(stats_rows):
                    break
                
                stats_row = stats_rows[stats_row_idx]
                cells = stats_row.find_all(['td', 'th'])
                if len(cells) < max(header_indices.values()) + 1:
                    stats_row_idx += 1  # Move to next row
                    continue
                
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Extract stats
                minutes = 0
                points = 0
                rebounds = 0
                assists = 0
                
                if 'MIN' in header_indices:
                    min_val = cell_texts[header_indices['MIN']]
                    minutes = self._parse_minutes(min_val)
                
                if 'PTS' in header_indices and header_indices['PTS'] < len(cell_texts):
                    try:
                        pts_val = cell_texts[header_indices['PTS']].strip()
                        # Make sure we're not getting an empty string or non-numeric value
                        if pts_val and pts_val != '':
                            points = int(float(pts_val))
                        else:
                            points = 0
                    except (ValueError, TypeError, IndexError) as e:
                        # Log error for debugging but don't fail completely
                        if player_idx < 3:  # Only log first few to avoid spam
                            print(f"      ⚠️  Error parsing points for {player_name}: '{cell_texts[header_indices['PTS']] if header_indices['PTS'] < len(cell_texts) else 'N/A'}' - {e}")
                        points = 0
                
                if 'REB' in header_indices and header_indices['REB'] < len(cell_texts):
                    try:
                        rebounds = int(float(cell_texts[header_indices['REB']]))
                    except:
                        pass
                
                if 'AST' in header_indices and header_indices['AST'] < len(cell_texts):
                    try:
                        ast_val = cell_texts[header_indices['AST']].strip()
                        if ast_val and ast_val != '':
                            assists = int(float(ast_val))
                        else:
                            assists = 0
                    except (ValueError, TypeError, IndexError) as e:
                        # Log error for debugging
                        if player_idx < 3:  # Only log first few to avoid spam
                            print(f"      ⚠️  Error parsing assists for {player_name}: '{cell_texts[header_indices['AST']] if header_indices['AST'] < len(cell_texts) else 'N/A'}' - {e}")
                        assists = 0
                
                # VALIDATION: Check if stats make sense (catch column misalignment)
                # If assists are suspiciously high (>15) but points are low (<10), likely wrong column
                if assists > 15 and points < 10 and minutes > 0:
                    print(f"      ⚠️  SUSPICIOUS: {player_name} has {assists} assists but only {points} points (MIN: {minutes:.1f})")
                    print(f"      📍 Full row: {cell_texts}")
                    print(f"      📍 Header indices: MIN={header_indices.get('MIN')}, PTS={header_indices.get('PTS')}, REB={header_indices.get('REB')}, AST={header_indices.get('AST')}")
                    # Try to find assists in nearby columns (might be misaligned)
                    # For now, set assists to 0 to prevent bad data
                    assists = 0
                
                # Increment stats_row_idx for next iteration (IMPORTANT: do this before continue/break)
                stats_row_idx += 1
                
                # VALIDATION: Check row alignment - if minutes is 0 but we have other stats, likely misaligned
                # Also check if stats seem reasonable (minutes should be > 0 if player has points/rebounds/assists)
                has_stats = points > 0 or rebounds > 0 or assists > 0
                if minutes == 0 and has_stats:
                    print(f"      ⚠️  WARNING: {player_name} has stats ({points} PTS, {rebounds} REB, {assists} AST) but 0 minutes - possible row misalignment")
                    print(f"      📍 Full row: {cell_texts}")
                    # Skip this row - likely misaligned
                    continue
                
                # Only add if player played (minutes > 0)
                if minutes > 0:
                    # Find player in database
                    player = self._find_player_by_name(player_name, current_team_id)
                    if not player:
                        player = self._find_player_by_name(player_name, None)
                    
                    if player:
                        # Use the detected team from box score, not player's current_team_id
                        # This ensures we assign the correct team even if player's current_team_id is outdated
                        team_id_to_use = current_team_id if current_team_id else player.current_team_id
                        
                        # Update player's current_team_id if it's different (player may have been traded)
                        if current_team_id and player.current_team_id != current_team_id:
                            print(f"      📝 Updating {player.name} team from {player.current_team_id} to {current_team_id}")
                            player.current_team_id = current_team_id
                            self.db.add(player)
                        
                        # Debug: Log all players to verify we're getting correct stats
                        # This helps catch issues like grabbing 3PM instead of PTS
                        # Log especially for players with suspicious stats
                        should_log = (
                            len(stats['player_stats']) < 5 or  # First 5 players
                            (points > 0 and points < 5 and minutes > 15) or  # Suspiciously low points
                            'Thomas' in player_name or 'Cam' in player_name  # Cam Thomas specifically
                        )
                        
                        # Enhanced logging for suspicious stats
                        should_log = (
                            len(stats['player_stats']) < 5 or  # First 5 players
                            (points > 0 and points < 5 and minutes > 15) or  # Suspiciously low points
                            (assists > 15 and points < 10) or  # Suspiciously high assists vs low points
                            'Thomas' in player_name or 'Cam' in player_name or 'Kuzma' in player_name  # Specific players to monitor
                        )
                        
                        if should_log:
                            print(f"      ✅ {player_name} (DB: {player.name}): {points} PTS, {rebounds} REB, {assists} AST (MIN: {minutes:.1f})")
                            if 'PTS' in header_indices:
                                pts_col = header_indices['PTS']
                                ast_col = header_indices.get('AST')
                                if pts_col < len(cell_texts):
                                    print(f"      📍 Raw PTS cell value: '{cell_texts[pts_col]}' (index {pts_col})")
                                    if ast_col is not None and ast_col < len(cell_texts):
                                        print(f"      📍 Raw AST cell value: '{cell_texts[ast_col]}' (index {ast_col})")
                                    print(f"      📍 Full row: {cell_texts}")
                                    print(f"      📍 Header: MIN={header_indices.get('MIN')}, PTS={header_indices.get('PTS')}, REB={header_indices.get('REB')}, AST={header_indices.get('AST')}")
                        
                        stats['player_stats'].append({
                            'player_id': player.player_id,
                            'team_id': team_id_to_use,
                            'minutes_played': minutes,
                            'points': points,
                            'rebounds': rebounds,
                            'assists': assists
                        })
                    else:
                        # Debug unmatched players (limit output)
                        if len(stats['player_stats']) < 5:
                            print(f"      ⚠️  Could not find: {player_name} (team_id={current_team_id})")
        
        return stats
    
    def _parse_espn_box_score_old(self, soup: BeautifulSoup, game: Game, home_team: Team, away_team: Team) -> Dict:
        """OLD PARSER - kept for reference. ESPN structure changed."""
        stats = {
            'game_id': game.game_id,
            'player_stats': []
        }
        
        # ESPN box score structure: Look for tables with player stats
        # Try multiple selectors to find the box score tables
        tables = soup.find_all('table')
        
        # Also look for divs with box score data
        box_score_sections = soup.find_all(['div', 'section'], class_=re.compile(r'box|score|player', re.I))
        
        # Track which team we're currently parsing
        # Start with away team (usually first in box scores)
        current_team_id = away_team.team_id
        
        # Parse tables
        for table in tables:
            # Skip if table doesn't look like a player stats table
            table_text = table.get_text()
            if 'MIN' not in table_text and 'PTS' not in table_text:
                continue
            
            # Try to determine team from table context
            table_parent = table.find_parent(['div', 'section'])
            if table_parent:
                parent_text = table_parent.get_text().upper()
                # Check for team names/abbreviations in parent
                if home_team.abbreviation.upper() in parent_text or home_team.name.upper() in parent_text:
                    current_team_id = home_team.team_id
                elif away_team.abbreviation.upper() in parent_text or away_team.name.upper() in parent_text:
                    current_team_id = away_team.team_id
                # Also check for common team name words
                elif any(word in parent_text for word in home_team.name.upper().split() if len(word) > 3):
                    current_team_id = home_team.team_id
                elif any(word in parent_text for word in away_team.name.upper().split() if len(word) > 3):
                    current_team_id = away_team.team_id
            
            # Extract player rows (skip header rows)
            rows = table.find_all('tr')
            
            # Find header row to determine column positions
            header_row = None
            header_indices = {}  # Map stat name to column index
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True).upper() for cell in cells]
                
                # Check if this is a header row
                if 'MIN' in cell_texts and 'PTS' in cell_texts:
                    header_row = row
                    for idx, text in enumerate(cell_texts):
                        if text in ['MIN', 'PTS', 'REB', 'AST']:
                            header_indices[text] = idx
                    break
            
            if not header_indices:
                continue  # Can't parse without header
            
            # Parse player rows
            for row in rows:
                # Skip header row
                if row == header_row:
                    continue
                
                cells = row.find_all(['td', 'th'])
                if len(cells) < max(header_indices.values()) + 1:
                    continue
                
                # Extract player name - look for link first, then try first cell
                player_link = row.find('a', href=re.compile(r'/player/'))
                player_name = None
                
                if player_link:
                    player_name = player_link.get_text(strip=True)
                else:
                    # Try first cell as player name
                    first_cell = cells[0]
                    player_name = first_cell.get_text(strip=True)
                    # Clean up name (remove extra whitespace, special chars)
                    player_name = re.sub(r'\s+', ' ', player_name).strip()
                
                if not player_name or len(player_name) < 2:
                    continue
                
                # Skip if it's a totals row or header
                if player_name.upper() in ['TOTALS', 'TEAM', 'STARTERS', 'BENCH', 'DNP', 'TEAM TOTALS']:
                    continue
                
                # Extract stats using header indices
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                minutes = 0
                points = 0
                rebounds = 0
                assists = 0
                
                # Get stats from known column positions
                if 'MIN' in header_indices:
                    min_idx = header_indices['MIN']
                    if min_idx < len(cell_texts):
                        minutes = self._parse_minutes(cell_texts[min_idx])
                
                if 'PTS' in header_indices:
                    pts_idx = header_indices['PTS']
                    if pts_idx < len(cell_texts):
                        try:
                            points = int(float(cell_texts[pts_idx]))
                        except:
                            pass
                
                if 'REB' in header_indices:
                    reb_idx = header_indices['REB']
                    if reb_idx < len(cell_texts):
                        try:
                            rebounds = int(float(cell_texts[reb_idx]))
                        except:
                            pass
                
                if 'AST' in header_indices:
                    ast_idx = header_indices['AST']
                    if ast_idx < len(cell_texts):
                        try:
                            assists = int(float(cell_texts[ast_idx]))
                        except:
                            pass
                
                # Only add if we have at least minutes (player played)
                if minutes > 0:
                    # Find player in database
                    player = self._find_player_by_name(player_name, current_team_id)
                    if not player:
                        # Try without team filter
                        player = self._find_player_by_name(player_name, None)
                    
                    if player:
                        stats['player_stats'].append({
                            'player_id': player.player_id,
                            'team_id': current_team_id or player.current_team_id,
                            'minutes_played': minutes,
                            'points': points,
                            'rebounds': rebounds,
                            'assists': assists
                        })
                    else:
                        # Debug: log unmatched players (limit to avoid spam)
                        if len(stats['player_stats']) < 3:
                            print(f"    ⚠️  Could not find player in database: {player_name} (team_id={current_team_id})")
        
        # Debug: log parsing results
        if len(stats['player_stats']) == 0:
            print(f"    ⚠️  Parser found 0 player stats (checked {len(tables)} tables)")
        
        return stats
    
    def scrape_rotowire_box_score(self, game_id: int) -> Optional[Dict]:
        """
        Scrape box score from Rotowire for a specific game.
        
        Args:
            game_id: Game ID in our database
        
        Returns:
            Dict with player stats, or None if not found
        """
        self._rate_limit()
        
        try:
            # Get game from database
            game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                return None
            
            # Rotowire box score URL (format may vary)
            date_str = game.game_date.strftime('%Y-%m-%d')
            
            # Try to find Rotowire game page
            # This is a placeholder - actual URL structure may need to be determined
            url = f"https://www.rotowire.com/basketball/boxscore.php?date={date_str}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            home_team = self.db.query(Team).filter(Team.team_id == game.home_team_id).first()
            away_team = self.db.query(Team).filter(Team.team_id == game.away_team_id).first()
            
            if not home_team or not away_team:
                return None
            
            # Parse box score (similar structure to ESPN)
            return self._parse_rotowire_box_score(soup, game, home_team, away_team)
            
        except Exception as e:
            print(f"Error scraping Rotowire box score for game {game_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _parse_rotowire_box_score(self, soup: BeautifulSoup, game: Game, home_team: Team, away_team: Team) -> Dict:
        """Parse Rotowire box score HTML."""
        stats = {
            'game_id': game.game_id,
            'player_stats': []
        }
        
        # Similar parsing logic to ESPN
        # Implementation would depend on Rotowire's HTML structure
        # This is a placeholder structure
        
        return stats
    
    def _parse_minutes(self, minutes_str: str) -> float:
        """Parse minutes string (e.g., '32:15' or '32.5') to float."""
        try:
            if ':' in minutes_str:
                parts = minutes_str.split(':')
                return float(parts[0]) + float(parts[1]) / 60.0
            else:
                return float(minutes_str)
        except:
            return 0.0
    
    def _parse_stat(self, stat_str: str) -> int:
        """Parse stat string to integer."""
        try:
            # Remove any non-numeric characters except decimal point
            stat_str = re.sub(r'[^\d.]', '', stat_str)
            return int(float(stat_str))
        except:
            return 0
    
    def save_box_score_to_db(self, box_score_data: Dict) -> Dict[str, int]:
        """
        Save box score data to database.
        
        Returns:
            Dict with 'created' and 'updated' counts
        """
        created_count = 0
        updated_count = 0
        
        try:
            game_id = box_score_data['game_id']
            
            # Get game to determine opponent team
            game = self.db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                print(f"  ⚠️  Game {game_id} not found in database")
                return {"created": 0, "updated": 0}
            
            for player_stat in box_score_data.get('player_stats', []):
                # Determine opponent team
                player_team_id = player_stat['team_id']
                if player_team_id == game.home_team_id:
                    opponent_team_id = game.away_team_id
                elif player_team_id == game.away_team_id:
                    opponent_team_id = game.home_team_id
                else:
                    # Fallback: use the other team
                    opponent_team_id = game.away_team_id if player_team_id == game.home_team_id else game.home_team_id
                
                # Check if stat already exists
                existing = self.db.query(PlayerGameStat).filter(
                    PlayerGameStat.game_id == game_id,
                    PlayerGameStat.player_id == player_stat['player_id']
                ).first()
                
                if existing:
                    # Update existing stat (this allows fixing incorrect data)
                    existing.minutes_played = player_stat.get('minutes_played', 0)
                    existing.points = player_stat.get('points', 0)
                    existing.rebounds = player_stat.get('rebounds', 0)
                    existing.assists = player_stat.get('assists', 0)
                    existing.opponent_team_id = opponent_team_id  # Update opponent too
                    updated_count += 1
                else:
                    # Create new stat
                    new_stat = PlayerGameStat(
                        game_id=game_id,
                        player_id=player_stat['player_id'],
                        team_id=player_stat['team_id'],
                        opponent_team_id=opponent_team_id,  # Required field
                        minutes_played=player_stat.get('minutes_played', 0),
                        points=player_stat.get('points', 0),
                        rebounds=player_stat.get('rebounds', 0),
                        assists=player_stat.get('assists', 0)
                    )
                    self.db.add(new_stat)
                    created_count += 1
            
            self.db.commit()
            return {"created": created_count, "updated": updated_count}
            
        except Exception as e:
            print(f"Error saving box score to database: {e}")
            self.db.rollback()
            raise
    
    def collect_box_scores_for_date(self, game_date: date, force_rescrape: bool = False) -> Dict[str, int]:
        """
        Collect box scores for all finished games on a specific date from ESPN.
        
        Args:
            game_date: Date to collect box scores for
            force_rescrape: If True, re-scrape even if stats already exist (useful for fixing incorrect data)
        
        Returns:
            Dict with counts of games processed and stats created
        """
        from app.models.game import Game
        from sqlalchemy import and_
        
        results = {
            "games_processed": 0,
            "stats_created": 0,
            "stats_updated": 0,
            "games_found": 0
        }
        
        try:
            # Get all games for this date (including scheduled/in_progress that might be finished)
            # We'll check for box scores regardless of status - if a game has box scores, it's finished
            games = self.db.query(Game).filter(
                Game.game_date == game_date
            ).all()
            
            if not games:
                return results
            
            # Filter to games that need stats
            # If force_rescrape is True, include all games (will update existing stats)
            # Otherwise, only include games without stats
            games_needing_stats = []
            for game in games:
                stats_count = self.db.query(func.count(PlayerGameStat.stat_id)).filter(
                    PlayerGameStat.game_id == game.game_id
                ).scalar()
                
                if force_rescrape or stats_count == 0:
                    games_needing_stats.append(game)
            
            if not games_needing_stats:
                return results
            
            games = games_needing_stats
            
            # Go to ESPN scoreboard for the date
            date_str = game_date.strftime('%Y%m%d')
            scoreboard_url = f"https://www.espn.com/nba/scoreboard/_/date/{date_str}"
            
            self._rate_limit()
            response = requests.get(scoreboard_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract gameIds from the scoreboard page
            # ESPN embeds gameIds in various places: data attributes, URLs, etc.
            game_ids = set()
            
            # Method 1: Look for gameId in data attributes
            elements_with_gameid = soup.find_all(attrs={'data-gameid': True})
            for elem in elements_with_gameid:
                game_id = elem.get('data-gameid')
                if game_id:
                    game_ids.add(game_id)
            
            # Method 2: Look for gameId in hrefs
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                # Extract gameId from URLs like /nba/game/_/gameId/401810318
                match = re.search(r'gameId[/=](\d+)', href)
                if match:
                    game_ids.add(match.group(1))
            
            # Method 3: Look in script tags (ESPN often embeds data in JSON)
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string:
                    # Look for gameId patterns in JavaScript
                    matches = re.findall(r'gameId["\']?\s*[:=]\s*["\']?(\d+)', script.string)
                    game_ids.update(matches)
            
            print(f"  Found {len(game_ids)} game IDs on ESPN scoreboard for {game_date}")
            
            # Build boxscore URLs from gameIds
            boxscore_links = [f"https://www.espn.com/nba/boxscore/_/gameId/{game_id}" for game_id in game_ids]
            
            # For each game in our database, try to find matching boxscore
            for game in games:
                home_team = self.db.query(Team).filter(Team.team_id == game.home_team_id).first()
                away_team = self.db.query(Team).filter(Team.team_id == game.away_team_id).first()
                
                if not home_team or not away_team:
                    continue
                
                # Check if game already has stats (only skip if not force_rescrape)
                if not force_rescrape:
                    stats_count = self.db.query(func.count(PlayerGameStat.stat_id)).filter(
                        PlayerGameStat.game_id == game.game_id
                    ).scalar()
                    
                    if stats_count > 0:
                        continue  # Already have stats (and not forcing re-scrape)
                
                # Try each boxscore link to find our game
                # IMPORTANT: Use page title as primary matching source (most reliable)
                for boxscore_url in boxscore_links:
                    try:
                        self._rate_limit()
                        box_response = requests.get(boxscore_url, headers=self.headers, timeout=15)
                        box_response.raise_for_status()
                        
                        box_soup = BeautifulSoup(box_response.content, 'html.parser')
                        
                        # Get page title - this is the most reliable source for team matching
                        page_title = box_soup.find('title')
                        title_text = page_title.get_text().upper() if page_title else ""
                        
                        # Get team names and abbreviations
                        home_abbrev = home_team.abbreviation.upper()
                        away_abbrev = away_team.abbreviation.upper()
                        home_name = home_team.name.upper()
                        away_name = away_team.name.upper()
                        
                        # PRIMARY MATCHING: Use page title (most reliable)
                        # ESPN title format: "Bucks 122-121 Hornets (Jan 2, 2026) Box Score - ESPN"
                        # Both team names/abbreviations should be in the title
                        title_has_home = (
                            home_abbrev in title_text or
                            any(word in title_text for word in home_name.split() if len(word) > 3)
                        )
                        title_has_away = (
                            away_abbrev in title_text or
                            any(word in title_text for word in away_name.split() if len(word) > 3)
                        )
                        
                        # Match if both teams are in the title (most reliable indicator)
                        if title_has_home and title_has_away:
                            # This is our game! Parse and save
                            print(f"  📊 Parsing box score for {away_team.abbreviation} @ {home_team.abbreviation}...")
                            box_score_data = self._parse_espn_box_score(box_soup, game, home_team, away_team)
                            
                            if box_score_data and box_score_data.get('player_stats'):
                                # Extract and store ESPN game ID from URL for future direct access
                                # URL format: https://www.espn.com/nba/boxscore/_/gameId/401810336
                                espn_game_id_match = re.search(r'gameId[/=](\d+)', boxscore_url)
                                if espn_game_id_match:
                                    espn_game_id = espn_game_id_match.group(1)
                                    if game.espn_game_id != espn_game_id:
                                        game.espn_game_id = espn_game_id
                                        print(f"  📌 Stored ESPN Game ID: {espn_game_id} for future direct access")
                                
                                # Save to database (will update existing stats if force_rescrape)
                                save_result = self.save_box_score_to_db(box_score_data)
                                
                                # Update game status to 'finished' if we found box scores
                                if game.game_status != 'finished':
                                    game.game_status = 'finished'
                                    print(f"  📝 Updated game status to 'finished'")
                                
                                self.db.commit()  # Commit after each game
                                results["games_processed"] += 1
                                results["stats_created"] += save_result.get("created", 0)
                                results["stats_updated"] += save_result.get("updated", 0)
                                results["games_found"] += 1
                                total_stats = save_result.get("created", 0) + save_result.get("updated", 0)
                                if save_result.get("updated", 0) > 0:
                                    print(f"  ✅ Updated {save_result.get('updated', 0)} and created {save_result.get('created', 0)} player stats for {away_team.abbreviation} @ {home_team.abbreviation}")
                                else:
                                    print(f"  ✅ Collected {total_stats} player stats for {away_team.abbreviation} @ {home_team.abbreviation}")
                                break  # Found our game, move to next
                            else:
                                print(f"  ⚠️  No player stats found for {away_team.abbreviation} @ {home_team.abbreviation}")
                        else:
                            # Debug: print why match failed (only for first few attempts to avoid spam)
                            if results["games_found"] < 2:
                                print(f"  🔍 Match check for {away_team.abbreviation} @ {home_team.abbreviation}: home={title_has_home}, away={title_has_away}")
                    
                    except Exception as e:
                        print(f"  ⚠️  Error fetching box score {boxscore_url}: {str(e)[:100]}")
                        continue
            
            return results
            
        except Exception as e:
            print(f"Error collecting box scores for {game_date}: {e}")
            import traceback
            traceback.print_exc()
            return results
    
    def close(self):
        """Close database session if we created it."""
        if hasattr(self, 'db') and self.db:
            self.db.close()

