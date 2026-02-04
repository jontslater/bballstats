"""
Injury Scraper

Scrapes injury data from various sources.
"""
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import List, Dict, Optional
from datetime import date, datetime
from app.services.injury_service import InjuryService
from app.models.player import Player
from app.models.team import Team
from app.database import SessionLocal


class InjuryScraper:
    """Scrape injury data from various sources."""
    
    def __init__(self, db_session=None, delay: float = 1.0):
        if db_session:
            self.db = db_session
            self.injury_service = InjuryService(db_session)
        else:
            self.db = SessionLocal()
            self.injury_service = InjuryService(self.db)
        
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
    
    def _find_player_by_name(self, player_name: str, team_abbreviation: Optional[str] = None) -> Optional[Player]:
        """Find a player by name, optionally filtering by team."""
        # Try exact match first
        query = self.db.query(Player).filter(Player.name.ilike(player_name))
        if team_abbreviation:
            team = self.db.query(Team).filter(Team.abbreviation.ilike(team_abbreviation)).first()
            if team:
                query = query.filter(Player.current_team_id == team.team_id)
        
        player = query.first()
        if player:
            return player
        
        # Try partial match (last name)
        name_parts = player_name.strip().split()
        if len(name_parts) > 1:
            last_name = name_parts[-1]
            query = self.db.query(Player).filter(Player.name.ilike(f'%{last_name}%'))
            if team_abbreviation:
                team = self.db.query(Team).filter(Team.abbreviation.ilike(team_abbreviation)).first()
                if team:
                    query = query.filter(Player.current_team_id == team.team_id)
            
            # If multiple matches, prefer exact last name match
            players = query.all()
            if len(players) == 1:
                return players[0]
            elif len(players) > 1:
                # Try to match by first name too
                first_name = name_parts[0]
                for p in players:
                    if p.name.startswith(first_name):
                        return p
                # Return first match if no first name match
                return players[0]
        
        return None
    
    def scrape_nba_com(self) -> List[Dict]:
        """
        Scrape injury data from NBA.com.
        
        TODO: Implement actual scraping logic.
        For now, returns empty list.
        
        Returns:
            List of injury dictionaries
        """
        # Placeholder for NBA.com scraping
        # This would use requests/BeautifulSoup to scrape NBA.com injury reports
        return []
    
    def scrape_espn(self) -> List[Dict]:
        """
        Scrape injury data from ESPN NBA injury report.
        
        Returns:
            List of injury dictionaries
        """
        self._rate_limit()
        
        try:
            # ESPN NBA injury report URL
            url = "https://www.espn.com/nba/injuries"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            injuries = []
            
            # ESPN structures injuries in tables, organized by team
            # Look for all tables on the page
            all_tables = soup.find_all('table')
            
            # Also try finding table rows directly
            rows = soup.find_all('tr')
            
            # If we found tables, extract rows from them
            if all_tables:
                for table in all_tables:
                    table_rows = table.find_all('tr')
                    rows.extend(table_rows)
            
            # Remove duplicates while preserving order
            seen_rows = set()
            unique_rows = []
            for row in rows:
                row_id = id(row)
                if row_id not in seen_rows:
                    seen_rows.add(row_id)
                    unique_rows.append(row)
            rows = unique_rows
            
            current_team = None
            for row in rows:
                # Try to extract team name from row or nearby elements
                team_elem = row.find_previous(['h2', 'h3', 'div'], class_=re.compile(r'team|name', re.I))
                if team_elem:
                    team_text = team_elem.get_text(strip=True)
                    # Extract team abbreviation (usually 3 letters)
                    team_match = re.search(r'\b([A-Z]{2,3})\b', team_text)
                    if team_match:
                        current_team = team_match.group(1)
                
                # Extract player name
                player_elem = row.find(['a', 'span', 'td'], class_=re.compile(r'player|name', re.I))
                if not player_elem:
                    player_elem = row.find('a', href=re.compile(r'/player/'))
                
                if not player_elem:
                    continue
                
                player_name = player_elem.get_text(strip=True)
                if not player_name:
                    continue
                
                # Extract status (Out, Questionable, Doubtful, Probable)
                # Look in all cells for status keywords
                status_text = None
                status_elem = None
                
                # Get all cells in the row
                cells = row.find_all('td')
                
                for cell in cells:
                    cell_text = cell.get_text(strip=True).upper()
                    # Check for status keywords
                    if any(s in cell_text for s in ['OUT', 'QUESTIONABLE', 'DOUBTFUL', 'PROBABLE', 'GTD', 'DAY-TO-DAY']):
                        status_elem = cell
                        status_text = cell_text
                        break
                
                # If not found in cells, try looking in the row text
                if not status_text:
                    row_text = row.get_text(strip=True).upper()
                    if 'OUT' in row_text:
                        status_text = 'OUT'
                    elif 'DOUBTFUL' in row_text:
                        status_text = 'DOUBTFUL'
                    elif 'QUESTIONABLE' in row_text or 'GTD' in row_text:
                        status_text = 'QUESTIONABLE'
                    elif 'PROBABLE' in row_text:
                        status_text = 'PROBABLE'
                    elif 'DAY-TO-DAY' in row_text:
                        status_text = 'QUESTIONABLE'  # Map day-to-day to questionable
                
                if not status_text:
                    continue
                
                # Map ESPN status to our status
                if 'OUT' in status_text:
                    status = 'Out'
                elif 'DOUBTFUL' in status_text:
                    status = 'Doubtful'
                elif 'QUESTIONABLE' in status_text or 'GTD' in status_text:
                    status = 'Questionable'
                elif 'PROBABLE' in status_text:
                    status = 'Probable'
                else:
                    continue  # Skip if status unclear
                
                # Extract injury type/description
                desc_elem = row.find(['span', 'td'], class_=re.compile(r'description|injury|note', re.I))
                if not desc_elem:
                    # Try finding description in remaining cells
                    cells = row.find_all('td')
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        if len(cell_text) > 20 and cell != player_elem.parent and cell != status_elem:
                            desc_elem = cell
                            break
                
                description = desc_elem.get_text(strip=True) if desc_elem else None
                
                # Find player in database
                player = self._find_player_by_name(player_name, current_team)
                if not player:
                    # Skip if player not found
                    continue
                
                injuries.append({
                    'player_id': player.player_id,
                    'player_name': player_name,
                    'status': status,
                    'injury_date': date.today(),  # ESPN doesn't always show injury date
                    'description': description,
                    'source': 'espn'
                })
            
            return injuries
            
        except Exception as e:
            print(f"Error scraping ESPN injuries: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def scrape_rotowire(self) -> List[Dict]:
        """
        Scrape injury data from Rotowire NBA injury report.
        
        Returns:
            List of injury dictionaries
        """
        self._rate_limit()
        
        try:
            # Rotowire NBA injury report URL
            url = "https://www.rotowire.com/basketball/injury-report.php"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            injuries = []
            
            # Rotowire structures injuries in tables
            # Look for injury table
            injury_table = soup.find('table', class_=re.compile(r'injury|player', re.I))
            if not injury_table:
                # Try finding any table
                injury_table = soup.find('table')
            
            if not injury_table:
                return []
            
            rows = injury_table.find_all('tr')[1:]  # Skip header row
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue
                
                # Extract player name (usually first cell)
                player_elem = cells[0].find('a') or cells[0]
                player_name = player_elem.get_text(strip=True)
                if not player_name:
                    continue
                
                # Extract team (usually second cell or in player link)
                team_text = ''
                if len(cells) > 1:
                    team_text = cells[1].get_text(strip=True)
                if not team_text and player_elem.get('href'):
                    # Try to extract from URL
                    href = player_elem.get('href', '')
                    team_match = re.search(r'/team/([a-z]+)', href)
                    if team_match:
                        team_text = team_match.group(1).upper()
                
                # Extract status
                status_text = ''
                if len(cells) > 2:
                    status_text = cells[2].get_text(strip=True).upper()
                elif len(cells) > 3:
                    status_text = cells[3].get_text(strip=True).upper()
                
                # Map Rotowire status to our status
                if 'OUT' in status_text:
                    status = 'Out'
                elif 'DOUBTFUL' in status_text:
                    status = 'Doubtful'
                elif 'QUESTIONABLE' in status_text or 'GTD' in status_text:
                    status = 'Questionable'
                elif 'PROBABLE' in status_text:
                    status = 'Probable'
                else:
                    continue  # Skip if status unclear
                
                # Extract injury type/description
                description = None
                if len(cells) > 3:
                    description = cells[3].get_text(strip=True)
                elif len(cells) > 4:
                    description = cells[4].get_text(strip=True)
                
                # Find player in database
                team_abbrev = None
                if team_text:
                    # Try to match team abbreviation
                    team = self.db.query(Team).filter(
                        Team.abbreviation.ilike(f'%{team_text[:3]}%')
                    ).first()
                    if team:
                        team_abbrev = team.abbreviation
                
                player = self._find_player_by_name(player_name, team_abbrev)
                if not player:
                    # Skip if player not found
                    continue
                
                injuries.append({
                    'player_id': player.player_id,
                    'player_name': player_name,
                    'status': status,
                    'injury_date': date.today(),
                    'description': description,
                    'source': 'rotowire'
                })
            
            return injuries
            
        except Exception as e:
            print(f"Error scraping Rotowire injuries: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def collect_all_injuries(self) -> Dict[str, int]:
        """
        Collect injuries from all sources.
        
        Returns:
            Dict with counts of injuries collected from each source
        """
        results = {
            "nba_com": 0,
            "espn": 0,
            "rotowire": 0,
            "total": 0
        }
        
        # Scrape from NBA.com
        try:
            nba_injuries = self.scrape_nba_com()
            for injury_data in nba_injuries:
                self._process_injury_data(injury_data)
                results["nba_com"] += 1
        except Exception as e:
            print(f"Error scraping NBA.com: {e}")
        
        # Scrape from ESPN
        try:
            espn_injuries = self.scrape_espn()
            for injury_data in espn_injuries:
                self._process_injury_data(injury_data)
                results["espn"] += 1
        except Exception as e:
            print(f"Error scraping ESPN: {e}")
        
        # Scrape from Rotowire
        try:
            rotowire_injuries = self.scrape_rotowire()
            for injury_data in rotowire_injuries:
                self._process_injury_data(injury_data)
                results["rotowire"] += 1
        except Exception as e:
            print(f"Error scraping Rotowire: {e}")
        
        results["total"] = results["nba_com"] + results["espn"] + results["rotowire"]
        
        return results
    
    def _process_injury_data(self, injury_data: Dict):
        """
        Process and store injury data.
        
        Args:
            injury_data: Dict with injury information
                - player_id (required)
                - status (required)
                - injury_date (required)
                - injury_type (optional)
                - description (optional)
                - expected_return_date (optional)
                - source (optional)
        """
        try:
            player_id = injury_data.get('player_id')
            if not player_id:
                return  # Skip if no player_id
            
            # Extract injury type from description if not provided
            injury_type = injury_data.get('injury_type')
            description = injury_data.get('description', '')
            
            if not injury_type and description:
                # Try to extract injury type from description (e.g., "ankle", "knee")
                common_injuries = ['ankle', 'knee', 'shoulder', 'back', 'hamstring', 'groin', 'wrist', 'hand', 'foot', 'calf', 'quad', 'achilles']
                desc_lower = description.lower()
                for injury in common_injuries:
                    if injury in desc_lower:
                        injury_type = injury.capitalize()
                        break
            
            # Create or update injury
            self.injury_service.create_or_update_injury(
                player_id=player_id,
                status=injury_data.get('status', 'Questionable'),
                injury_date=injury_data.get('injury_date', date.today()),
                injury_type=injury_type,
                description=description,
                expected_return_date=injury_data.get('expected_return_date'),
                source=injury_data.get('source', 'scraper')
            )
            
        except Exception as e:
            print(f"Error processing injury data: {e}")
            # Don't raise - continue processing other injuries
    
    def close(self):
        """Close database session if we created it."""
        if hasattr(self, 'db') and self.db:
            self.db.close()

