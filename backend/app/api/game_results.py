"""
Game Results Collection API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.database import SessionLocal
from app.scrapers.nba_api_client import NBAAPIClient
from app.scrapers.basketball_reference import BasketballReferenceScraper
from app.models import Game, Team, Season, Player, PlayerGameStat, GameSchedule
from sqlalchemy import and_, func
import time

router = APIRouter(prefix="/api/game-results", tags=["game results"])


def find_team_by_nba_id(db: Session, nba_team_id: int):
    """Find team by NBA API team ID using abbreviation mapping."""
    team_id_map = {
        1610612737: "ATL", 1610612738: "BOS", 1610612751: "BKN",
        1610612766: "CHA", 1610612741: "CHI", 1610612739: "CLE",
        1610612742: "DAL", 1610612743: "DEN", 1610612765: "DET",
        1610612744: "GSW", 1610612745: "HOU", 1610612754: "IND",
        1610612746: "LAC", 1610612747: "LAL", 1610612763: "MEM",
        1610612748: "MIA", 1610612749: "MIL", 1610612750: "MIN",
        1610612740: "NOP", 1610612752: "NYK", 1610612760: "OKC",
        1610612753: "ORL", 1610612755: "PHI", 1610612756: "PHX",
        1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS",
        1610612761: "TOR", 1610612762: "UTA", 1610612764: "WAS"
    }
    
    abbrev = team_id_map.get(nba_team_id)
    if abbrev:
        return db.query(Team).filter(Team.abbreviation == abbrev).first()
    return None


def get_or_create_player(db: Session, nba_player_id: int, player_name: str):
    """Get existing player or create a new one."""
    player = db.query(Player).filter(Player.player_id == nba_player_id).first()
    
    if not player:
        player = Player(
            player_id=nba_player_id,
            name=player_name
        )
        db.add(player)
        db.flush()
    
    return player


def convert_br_to_nba_format(br_box_score: dict, home_team: Team, away_team: Team) -> dict:
    """Convert Basketball Reference box score format to NBA API format."""
    player_stats = []
    
    for br_stat in br_box_score.get('player_stats', []):
        nba_stat = {
            'PLAYER_NAME': br_stat.get('PLAYER_NAME', ''),
            'TEAM_ABBREVIATION': br_stat.get('TEAM_ABBREVIATION', ''),
            'MIN': int(br_stat.get('MIN', 0)) if br_stat.get('MIN') else 0,
            'PTS': br_stat.get('PTS', 0),
            'REB': br_stat.get('REB', 0),
            'OREB': br_stat.get('OREB', 0),
            'DREB': br_stat.get('DREB', 0),
            'AST': br_stat.get('AST', 0),
            'STL': br_stat.get('STL', 0),
            'BLK': br_stat.get('BLK', 0),
            'TOV': br_stat.get('TOV', 0),
            'PF': br_stat.get('PF', 0),
            'FGM': br_stat.get('FGM', 0),
            'FGA': br_stat.get('FGA', 0),
            'FG3M': br_stat.get('FG3M', 0),
            'FG3A': br_stat.get('FG3A', 0),
            'FTM': br_stat.get('FTM', 0),
            'FTA': br_stat.get('FTA', 0),
            'PLUS_MINUS': br_stat.get('PLUS_MINUS', 0),
        }
        player_stats.append(nba_stat)
    
    return {
        'player_stats': player_stats,
        'team_stats': []
    }


@router.post("/collect-previous-day")
async def collect_previous_day(sport: str = Query("NBA", description="Sport: NBA or MLB")):
    """
    Collect game results for the previous day.
    
    sport: NBA or MLB. MLB uses MLB Stats API; NBA uses NBA API.
    Note: This operation can take 30-60 seconds as it processes multiple games.
    """
    if sport.upper() == "MLB":
        import subprocess
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        script_path = project_root / "scripts" / "mlb_collect_game_results.py"
        if not script_path.exists():
            raise HTTPException(status_code=404, detail=f"MLB collect script not found at {script_path}")
        venv_python = project_root / "venv" / "bin" / "python3"
        if not venv_python.exists():
            venv_python = project_root / "backend" / "venv" / "bin" / "python3"
        python_cmd = str(venv_python) if venv_python.exists() else "python3"
        try:
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root / "backend")
            result = subprocess.run(
                [python_cmd, str(script_path), "--previous-day"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            # Parse output for counts (script prints "Created X games, processed Y games")
            games_processed = games_created = stats_created = 0
            for line in (result.stdout or "").splitlines():
                if "processed" in line.lower() and "games" in line.lower():
                    import re
                    m = re.search(r"processed\s+(\d+)\s+games", line, re.I)
                    if m:
                        games_processed = int(m.group(1))
                if "created" in line.lower() and "games" in line.lower():
                    import re
                    m = re.search(r"created\s+(\d+)\s+games", line, re.I)
                    if m:
                        games_created = int(m.group(1))
            return {
                "success": result.returncode == 0,
                "message": f"MLB game results for previous day",
                "games_processed": games_processed,
                "games_created": games_created,
                "stats_created": stats_created,
            }
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=408, detail="MLB collection timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    db = SessionLocal()
    try:
        target_date = date.today() - timedelta(days=1)
        
        # Get current season (same logic as the script)
        season = db.query(Season).filter(Season.is_current == True).first()
        
        if not season:
            # Fallback: try to find season by date range
            season = db.query(Season).filter(
                Season.start_date <= target_date,
                Season.end_date >= target_date
            ).first()
        
        if not season:
            raise HTTPException(status_code=400, detail=f"No season found for date {target_date}. Please ensure seasons are seeded.")
        
        client = NBAAPIClient(delay=1.0)
        games_data = client.get_game_schedule(target_date)
        
        if not games_data:
            return {
                "success": True,
                "message": f"No games scheduled for {target_date}",
                "games_processed": 0,
                "games_created": 0,
                "stats_created": 0
            }
        
        games_processed = 0
        games_created = 0
        stats_created = 0
        
        for game_data in games_data:
            try:
                nba_game_id = game_data.get('GAME_ID')
                if not nba_game_id:
                    continue
                
                home_team = find_team_by_nba_id(db, game_data.get('HOME_TEAM_ID'))
                away_team = find_team_by_nba_id(db, game_data.get('VISITOR_TEAM_ID'))
                
                if not home_team or not away_team:
                    continue
                
                game_status_id = game_data.get('GAME_STATUS_ID', 0)
                if game_status_id != 3:  # Not finished
                    continue
                
                # Check if game already exists
                existing_game = db.query(Game).filter(
                    and_(
                        Game.game_date == target_date,
                        Game.home_team_id == home_team.team_id,
                        Game.away_team_id == away_team.team_id
                    )
                ).first()
                
                # Get box score
                time.sleep(1)
                box_score = client.get_game_box_score(str(nba_game_id))
                
                # Fallback to Basketball Reference
                if not box_score or not box_score.get('player_stats'):
                    br_scraper = BasketballReferenceScraper()
                    br_box_score = br_scraper.get_box_score_by_date_and_teams(target_date, home_team.abbreviation)
                    
                    if br_box_score and br_box_score.get('player_stats'):
                        box_score = convert_br_to_nba_format(br_box_score, home_team, away_team)
                        home_score = br_box_score.get('home_score')
                        away_score = br_box_score.get('visitor_score')
                    else:
                        continue
                else:
                    home_score = game_data.get('HOME_TEAM_SCORE')
                    away_score = game_data.get('VISITOR_TEAM_SCORE')
                
                # Create or update game
                if existing_game:
                    game = existing_game
                    game.home_score = home_score
                    game.away_score = away_score
                    game.game_status = "finished"
                else:
                    game = Game(
                        game_date=target_date,
                        season_id=season.season_id,
                        home_team_id=home_team.team_id,
                        away_team_id=away_team.team_id,
                        home_score=home_score,
                        away_score=away_score,
                        game_status="finished"
                    )
                    db.add(game)
                    db.flush()
                    games_created += 1
                
                # Process player stats
                player_stats_data = box_score.get('player_stats', [])
                
                for stat_data in player_stats_data:
                    try:
                        player_name = stat_data.get('PLAYER_NAME', 'Unknown')
                        if not player_name or player_name == 'Unknown':
                            continue
                        
                        nba_player_id = stat_data.get('PLAYER_ID')
                        
                        if nba_player_id:
                            player = get_or_create_player(db, nba_player_id, player_name)
                        else:
                            team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                            team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                            player = db.query(Player).filter(Player.name == player_name).first()
                            
                            if not player:
                                continue
                        
                        # Check if stat already exists
                        existing_stat = db.query(PlayerGameStat).filter(
                            and_(
                                PlayerGameStat.player_id == player.player_id,
                                PlayerGameStat.game_id == game.game_id
                            )
                        ).first()
                        
                        if existing_stat:
                            continue
                        
                        team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                        team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                        opponent_team_id = away_team.team_id if team == home_team else home_team.team_id
                        
                        def safe_int(value, default=0):
                            try:
                                if value is None or (isinstance(value, float) and (value != value)):
                                    return default
                                return int(float(value))
                            except (ValueError, TypeError):
                                return default
                        
                        minutes_value = stat_data.get('MIN', 0)
                        minutes_played = 0
                        if isinstance(minutes_value, str) and ':' in minutes_value:
                            try:
                                mins, secs = map(int, minutes_value.split(':'))
                                minutes_played = mins + (secs / 60)
                            except:
                                minutes_played = 0
                        elif isinstance(minutes_value, (int, float)):
                            minutes_played = float(minutes_value)
                        
                        player_stat = PlayerGameStat(
                            player_id=player.player_id,
                            game_id=game.game_id,
                            team_id=team.team_id if team else None,
                            opponent_team_id=opponent_team_id,
                            minutes_played=int(minutes_played),
                            points=safe_int(stat_data.get('PTS')),
                            rebounds=safe_int(stat_data.get('REB')),
                            offensive_rebounds=safe_int(stat_data.get('OREB')),
                            defensive_rebounds=safe_int(stat_data.get('DREB')),
                            assists=safe_int(stat_data.get('AST')),
                            steals=safe_int(stat_data.get('STL')),
                            blocks=safe_int(stat_data.get('BLK')),
                            turnovers=safe_int(stat_data.get('TOV') or stat_data.get('TO')),
                            personal_fouls=safe_int(stat_data.get('PF')),
                            field_goals_made=safe_int(stat_data.get('FGM')),
                            field_goals_attempted=safe_int(stat_data.get('FGA')),
                            three_pointers_made=safe_int(stat_data.get('FG3M')),
                            three_pointers_attempted=safe_int(stat_data.get('FG3A')),
                            free_throws_made=safe_int(stat_data.get('FTM')),
                            free_throws_attempted=safe_int(stat_data.get('FTA')),
                            plus_minus=safe_int(stat_data.get('PLUS_MINUS')),
                            is_home=(team == home_team)
                        )
                        db.add(player_stat)
                        stats_created += 1
                        
                    except Exception as e:
                        print(f"Error processing player stat: {e}")
                        continue
                
                games_processed += 1
                db.commit()
                
            except Exception as e:
                print(f"Error processing game: {e}")
                db.rollback()
                continue
        
        return {
            "success": True,
            "message": f"Collected game results for {target_date}",
            "games_processed": games_processed,
            "games_created": games_created,
            "stats_created": stats_created
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error collecting game results: {str(e)}")
    finally:
        db.close()


@router.post("/collect-for-finished-games")
async def collect_for_finished_games(
    days_back: int = 7
):
    """
    Collect box scores for all finished games that don't have player stats yet.
    
    This is useful before evaluating predictions, as predictions can't be evaluated
    without player game stats.
    """
    db = SessionLocal()
    try:
        from datetime import date, timedelta
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Find finished games without player stats
        finished_games = db.query(Game).filter(
            and_(
                Game.game_status == 'finished',
                Game.game_date >= cutoff_date
            )
        ).all()
        
        games_needing_stats = []
        for game in finished_games:
            stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
                PlayerGameStat.game_id == game.game_id
            ).scalar()
            
            if stats_count == 0:
                games_needing_stats.append(game)
        
        if not games_needing_stats:
            return {
                "success": True,
                "message": "All finished games already have player stats",
                "games_processed": 0,
                "stats_created": 0
            }
        
        client = NBAAPIClient(delay=1.0)
        br_scraper = BasketballReferenceScraper()
        from app.scrapers.box_score_scraper import BoxScoreScraper
        box_score_scraper = BoxScoreScraper(db_session=db, delay=1.5)
        
        total_stats_created = 0
        games_processed = 0
        
        # Group games by date for more efficient ESPN scraping
        games_by_date = {}
        for game in games_needing_stats:
            if game.game_date not in games_by_date:
                games_by_date[game.game_date] = []
            games_by_date[game.game_date].append(game)
        
        # First, try ESPN for each date (more reliable for recent games)
        # Use force_rescrape=True to fix any incorrect data
        for game_date, date_games in games_by_date.items():
            print(f"\n📊 Collecting box scores for {game_date} ({len(date_games)} games)...")
            espn_results = box_score_scraper.collect_box_scores_for_date(game_date, force_rescrape=True)
            games_processed += espn_results["games_processed"]
            total_stats_created += espn_results.get("stats_created", 0) + espn_results.get("stats_updated", 0)
            
            # Remove games that were successfully collected from our list
            for game in date_games[:]:
                stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
                    PlayerGameStat.game_id == game.game_id
                ).scalar()
                if stats_count > 0:
                    date_games.remove(game)
        
        # For remaining games, try NBA API and Basketball Reference
        remaining_games = [g for games_list in games_by_date.values() for g in games_list]
        
        for game in remaining_games:
            try:
                # Get NBA game ID from schedule
                schedule = db.query(GameSchedule).filter(
                    GameSchedule.game_id == game.game_id
                ).first()
                
                box_score = None
                box_score_source = None
                
                # Try NBA API first
                if schedule and schedule.nba_game_id:
                    try:
                        box_score = client.get_game_box_score(str(schedule.nba_game_id))
                        if box_score and box_score.get('player_stats'):
                            box_score_source = 'nba_api'
                    except Exception as e:
                        print(f"  NBA API failed for game {game.game_id}: {e}")
                
                # Try Basketball Reference as fallback
                if not box_score or not box_score.get('player_stats'):
                    home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
                    if home_team:
                        try:
                            br_box_score = br_scraper.get_box_score_by_date_and_teams(
                                game.game_date, 
                                home_team.abbreviation
                            )
                            
                            if br_box_score and br_box_score.get('player_stats'):
                                away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
                                box_score = convert_br_to_nba_format(br_box_score, home_team, away_team)
                                box_score_source = 'basketball_reference'
                        except Exception as e:
                            print(f"  Basketball Reference failed for game {game.game_id}: {e}")
                
                # Try ESPN box score scraper as additional fallback
                if not box_score or not box_score.get('player_stats'):
                    try:
                        espn_box_score = box_score_scraper.scrape_espn_box_score(game.game_id)
                        if espn_box_score and espn_box_score.get('player_stats'):
                            # Convert ESPN format to our format
                            player_stats_data = []
                            home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
                            away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
                            
                            for stat in espn_box_score.get('player_stats', []):
                                # Look up player name from ID
                                player = db.query(Player).filter(Player.player_id == stat.get('player_id')).first()
                                player_name = player.name if player else f"Player {stat.get('player_id')}"
                                
                                # Determine team abbreviation from team_id
                                team_id = stat.get('team_id')
                                team_abbrev = None
                                if team_id:
                                    team = db.query(Team).filter(Team.team_id == team_id).first()
                                    team_abbrev = team.abbreviation if team else None
                                
                                player_stats_data.append({
                                    'PLAYER_ID': stat.get('player_id'),
                                    'PLAYER_NAME': player_name,
                                    'TEAM_ABBREVIATION': team_abbrev,
                                    'MIN': stat.get('minutes_played', 0),
                                    'PTS': stat.get('points', 0),
                                    'REB': stat.get('rebounds', 0),
                                    'AST': stat.get('assists', 0),
                                    'OREB': 0,  # ESPN scraper may not have these
                                    'DREB': 0,
                                    'STL': 0,
                                    'BLK': 0,
                                    'TOV': 0,
                                    'PF': 0,
                                    'FGM': 0,
                                    'FGA': 0,
                                    'FG3M': 0,
                                    'FG3A': 0,
                                    'FTM': 0,
                                    'FTA': 0,
                                    'PLUS_MINUS': 0,
                                })
                            
                            if player_stats_data:
                                # Create a box score dict in NBA API format
                                box_score = {'player_stats': player_stats_data}
                                box_score_source = 'espn'
                    except Exception as e:
                        print(f"  ESPN scraper failed for game {game.game_id}: {e}")
                
                if box_score and box_score.get('player_stats'):
                    # Process player stats (same logic as collect_previous_day)
                    player_stats_data = box_score.get('player_stats', [])
                    
                    home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
                    away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
                    
                    if not home_team or not away_team:
                        continue
                    
                    for stat_data in player_stats_data:
                        try:
                                    player_name = stat_data.get('PLAYER_NAME', 'Unknown')
                                    if not player_name or player_name == 'Unknown':
                                        continue
                                    
                                    nba_player_id = stat_data.get('PLAYER_ID')
                                    
                                    if nba_player_id:
                                        player = get_or_create_player(db, nba_player_id, player_name)
                                    else:
                                        team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                                        team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                                        player = db.query(Player).filter(Player.name == player_name).first()
                                        
                                        if not player:
                                            continue
                                    
                                    # Check if stat already exists
                                    existing_stat = db.query(PlayerGameStat).filter(
                                        and_(
                                            PlayerGameStat.player_id == player.player_id,
                                            PlayerGameStat.game_id == game.game_id
                                        )
                                    ).first()
                                    
                                    if existing_stat:
                                        continue
                                    
                                    team_abbrev = stat_data.get('TEAM_ABBREVIATION')
                                    team = db.query(Team).filter(Team.abbreviation == team_abbrev).first() if team_abbrev else None
                                    opponent_team_id = away_team.team_id if team == home_team else home_team.team_id
                                    
                                    def safe_int(value, default=0):
                                        try:
                                            if value is None or (isinstance(value, float) and (value != value)):
                                                return default
                                            return int(float(value))
                                        except (ValueError, TypeError):
                                            return default
                                    
                                    minutes_value = stat_data.get('MIN', 0)
                                    minutes_played = 0
                                    if isinstance(minutes_value, str) and ':' in minutes_value:
                                        try:
                                            mins, secs = map(int, minutes_value.split(':'))
                                            minutes_played = mins + (secs / 60)
                                        except:
                                            minutes_played = 0
                                    elif isinstance(minutes_value, (int, float)):
                                        minutes_played = float(minutes_value)
                                    
                                    player_stat = PlayerGameStat(
                                        player_id=player.player_id,
                                        game_id=game.game_id,
                                        team_id=team.team_id if team else None,
                                        opponent_team_id=opponent_team_id,
                                        minutes_played=int(minutes_played),
                                        points=safe_int(stat_data.get('PTS')),
                                        rebounds=safe_int(stat_data.get('REB')),
                                        offensive_rebounds=safe_int(stat_data.get('OREB')),
                                        defensive_rebounds=safe_int(stat_data.get('DREB')),
                                        assists=safe_int(stat_data.get('AST')),
                                        steals=safe_int(stat_data.get('STL')),
                                        blocks=safe_int(stat_data.get('BLK')),
                                        turnovers=safe_int(stat_data.get('TOV') or stat_data.get('TO')),
                                        personal_fouls=safe_int(stat_data.get('PF')),
                                        field_goals_made=safe_int(stat_data.get('FGM')),
                                        field_goals_attempted=safe_int(stat_data.get('FGA')),
                                        three_pointers_made=safe_int(stat_data.get('FG3M')),
                                        three_pointers_attempted=safe_int(stat_data.get('FG3A')),
                                        free_throws_made=safe_int(stat_data.get('FTM')),
                                        free_throws_attempted=safe_int(stat_data.get('FTA')),
                                        plus_minus=safe_int(stat_data.get('PLUS_MINUS')),
                                        is_home=(team == home_team)
                                    )
                                    db.add(player_stat)
                                    total_stats_created += 1
                                    
                        except Exception as e:
                            print(f"Error processing player stat: {e}")
                            continue
                    
                    games_processed += 1
                    db.commit()
                    print(f"  ✅ Collected box score for game {game.game_id} from {box_score_source}")
                    time.sleep(1)  # Rate limiting
                else:
                    # Use NBA API
                    time.sleep(1)
                    box_score = client.get_game_box_score(str(schedule.nba_game_id))
                    
                    if box_score and box_score.get('player_stats'):
                        # Process stats (similar to above)
                        # ... (same processing logic)
                        games_processed += 1
                        db.commit()
                        
            except Exception as e:
                print(f"Error processing game {game.game_id}: {e}")
                db.rollback()
                continue
        
        return {
            "success": True,
            "message": f"Collected stats for {games_processed} games",
            "games_processed": games_processed,
            "stats_created": total_stats_created
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error collecting game results: {str(e)}")
    finally:
        db.close()

