#!/usr/bin/env python3
"""
Test the full prediction flow:
1. Verify lineups for games
2. Get box scores for finished games
3. Generate predictions based on lineups and other factors

Usage:
    python backend/scripts/test_full_prediction_flow.py [--date YYYY-MM-DD]
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
import argparse

# Add parent directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.models.game import Game
from app.models.team import Team
from app.models.player import Player
from app.models.lineup import Lineup
from app.models.player_game_stat import PlayerGameStat
from app.models.prediction import Prediction
from app.scrapers.box_score_scraper import BoxScoreScraper
from app.scrapers.lineup_scraper import LineupScraper
from app.services.prediction_service import PredictionService
from app.services.lineup_service import LineupService
from sqlalchemy import and_, func

def test_lineup_verification(db, game_date: date):
    """Test lineup verification for games on a specific date."""
    print("\n" + "="*80)
    print("STEP 1: VERIFYING LINEUPS")
    print("="*80)
    
    games = db.query(Game).filter(Game.game_date == game_date).all()
    
    if not games:
        print(f"❌ No games found for {game_date}")
        return False
    
    print(f"Found {len(games)} games for {game_date}\n")
    
    lineup_service = LineupService(db)
    lineup_scraper = LineupScraper(db)
    
    games_with_lineups = 0
    games_without_lineups = 0
    
    for game in games:
        home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
        away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
        
        print(f"\nGame {game.game_id}: {away_team.abbreviation if away_team else 'Away'} @ {home_team.abbreviation if home_team else 'Home'}")
        
        # Check if lineup is confirmed (check both teams)
        home_confirmed = lineup_service.is_lineup_confirmed(game.game_id, game.home_team_id)
        away_confirmed = lineup_service.is_lineup_confirmed(game.game_id, game.away_team_id)
        is_confirmed = home_confirmed or away_confirmed
        
        print(f"  Home lineup confirmed: {home_confirmed}")
        print(f"  Away lineup confirmed: {away_confirmed}")
        
        if is_confirmed:
            # Get players in lineup
            home_players = lineup_service.get_players_in_lineup(game.game_id, game.home_team_id)
            away_players = lineup_service.get_players_in_lineup(game.game_id, game.away_team_id)
            
            print(f"  Home team players: {len(home_players)} (starters + bench)")
            print(f"  Away team players: {len(away_players)} (starters + bench)")
            
            if home_players or away_players:
                games_with_lineups += 1
            else:
                games_without_lineups += 1
        else:
            games_without_lineups += 1
            print(f"  ⚠️  Lineup not confirmed - attempting to collect...")
            
            # Try to collect lineup
            try:
                lineup_scraper.collect_lineups_for_date(game_date)
                db.commit()
                
                # Check again
                home_confirmed_after = lineup_service.is_lineup_confirmed(game.game_id, game.home_team_id)
                away_confirmed_after = lineup_service.is_lineup_confirmed(game.game_id, game.away_team_id)
                is_confirmed_after = home_confirmed_after or away_confirmed_after
                if is_confirmed_after:
                    print(f"  ✅ Lineup collected successfully")
                    games_with_lineups += 1
                    games_without_lineups -= 1
                else:
                    print(f"  ❌ Still no lineup after collection attempt")
            except Exception as e:
                print(f"  ❌ Error collecting lineup: {e}")
    
    print(f"\n📊 Summary:")
    print(f"  Games with lineups: {games_with_lineups}")
    print(f"  Games without lineups: {games_without_lineups}")
    
    return games_with_lineups > 0

def test_box_score_collection(db, game_date: date):
    """Test box score collection for finished games."""
    print("\n" + "="*80)
    print("STEP 2: COLLECTING BOX SCORES FOR FINISHED GAMES")
    print("="*80)
    
    games = db.query(Game).filter(Game.game_date == game_date).all()
    
    finished_games = [g for g in games if g.game_status == 'finished']
    games_with_stats = []
    games_without_stats = []
    
    print(f"Found {len(finished_games)} finished games\n")
    
    box_scraper = BoxScoreScraper(db)
    
    for game in finished_games:
        home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
        away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
        
        print(f"\nGame {game.game_id}: {away_team.abbreviation if away_team else 'Away'} @ {home_team.abbreviation if home_team else 'Home'}")
        print(f"  ESPN Game ID: {game.espn_game_id or 'Not stored'}")
        
        # Check if we have stats
        stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
            PlayerGameStat.game_id == game.game_id
        ).scalar()
        
        if stats_count > 0:
            print(f"  ✅ Already has {stats_count} player stats")
            games_with_stats.append(game)
        else:
            print(f"  ⚠️  No stats found - attempting to collect...")
            games_without_stats.append(game)
    
    # Collect box scores for games without stats
    if games_without_stats:
        print(f"\n📥 Collecting box scores for {len(games_without_stats)} games...")
        try:
            result = box_scraper.collect_box_scores_for_date(game_date, force_rescrape=False)
            db.commit()
            
            print(f"\n📊 Collection Results:")
            print(f"  Games processed: {result.get('games_processed', 0)}")
            print(f"  Stats created: {result.get('stats_created', 0)}")
            print(f"  Stats updated: {result.get('stats_updated', 0)}")
            print(f"  Games found: {result.get('games_found', 0)}")
            
            # Re-check stats
            for game in games_without_stats:
                stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
                    PlayerGameStat.game_id == game.game_id
                ).scalar()
                
                if stats_count > 0:
                    games_with_stats.append(game)
                    print(f"  ✅ Game {game.game_id} now has {stats_count} stats")
        except Exception as e:
            print(f"  ❌ Error collecting box scores: {e}")
            import traceback
            traceback.print_exc()
    
    # Recalculate games without stats after collection
    final_games_without_stats = []
    for game in finished_games:
        stats_count = db.query(func.count(PlayerGameStat.stat_id)).filter(
            PlayerGameStat.game_id == game.game_id
        ).scalar()
        if stats_count == 0:
            final_games_without_stats.append(game)
    
    print(f"\n📊 Summary:")
    print(f"  Games with box scores: {len(games_with_stats)}")
    print(f"  Games without box scores: {len(final_games_without_stats)}")
    
    return len(games_with_stats) > 0

def test_prediction_generation(db, game_date: date):
    """Test prediction generation based on lineups and other factors."""
    print("\n" + "="*80)
    print("STEP 3: GENERATING PREDICTIONS BASED ON LINEUPS AND FACTORS")
    print("="*80)
    
    games = db.query(Game).filter(Game.game_date == game_date).all()
    
    # Only generate predictions for scheduled/in_progress games (not finished)
    games_to_predict = [g for g in games if g.game_status in ['scheduled', 'in_progress']]
    
    if not games_to_predict:
        print(f"⚠️  No scheduled/in_progress games for {game_date}")
        print(f"   (All games may be finished - predictions are typically generated before games)")
        return True
    
    print(f"Found {len(games_to_predict)} games to generate predictions for\n")
    
    prediction_service = PredictionService(db)
    lineup_service = LineupService(db)
    
    total_predictions = 0
    games_with_predictions = 0
    games_without_predictions = []
    
    for game in games_to_predict:
        home_team = db.query(Team).filter(Team.team_id == game.home_team_id).first()
        away_team = db.query(Team).filter(Team.team_id == game.away_team_id).first()
        
        print(f"\nGame {game.game_id}: {away_team.abbreviation if away_team else 'Away'} @ {home_team.abbreviation if home_team else 'Home'}")
        
        # Check if lineup is confirmed (check both teams)
        home_confirmed = lineup_service.is_lineup_confirmed(game.game_id, game.home_team_id)
        away_confirmed = lineup_service.is_lineup_confirmed(game.game_id, game.away_team_id)
        is_confirmed = home_confirmed or away_confirmed
        print(f"  Lineup confirmed: {is_confirmed} (Home: {home_confirmed}, Away: {away_confirmed})")
        
        # Check existing predictions
        existing_count = db.query(func.count(Prediction.prediction_id)).filter(
            Prediction.game_id == game.game_id
        ).scalar()
        
        if existing_count > 0:
            print(f"  ✅ Already has {existing_count} predictions")
            total_predictions += existing_count
            games_with_predictions += 1
        else:
            print(f"  ⚠️  No predictions - generating...")
            games_without_predictions.append(game)
    
    # Generate predictions for games without them
    if games_without_predictions:
        print(f"\n🔮 Generating predictions for {len(games_without_predictions)} games...")
        
        for game in games_without_predictions:
            try:
                print(f"\n  Generating predictions for Game {game.game_id}...")
                predictions = prediction_service.generate_predictions_for_game(
                    game.game_id,
                    stat_types=['points', 'rebounds', 'assists', 'three_pointers_made']
                )
                
                db.commit()
                
                count = len(predictions) if predictions else 0
                total_predictions += count
                
                if count > 0:
                    games_with_predictions += 1
                    print(f"  ✅ Generated {count} predictions")
                else:
                    print(f"  ⚠️  No predictions generated (may have been filtered out)")
            except Exception as e:
                print(f"  ❌ Error generating predictions: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n📊 Summary:")
    print(f"  Games with predictions: {games_with_predictions}")
    print(f"  Total predictions: {total_predictions}")
    
    return games_with_predictions > 0

def main():
    parser = argparse.ArgumentParser(description='Test full prediction flow')
    parser.add_argument('--date', type=str, help='Date to test (YYYY-MM-DD), defaults to today')
    args = parser.parse_args()
    
    if args.date:
        test_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        test_date = date.today()
    
    print("="*80)
    print(f"TESTING FULL PREDICTION FLOW FOR {test_date}")
    print("="*80)
    
    db = SessionLocal()
    try:
        # Step 1: Verify lineups
        lineups_ok = test_lineup_verification(db, test_date)
        
        # Step 2: Get box scores for finished games
        box_scores_ok = test_box_score_collection(db, test_date)
        
        # Step 3: Generate predictions
        predictions_ok = test_prediction_generation(db, test_date)
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        print(f"✅ Lineup verification: {'PASS' if lineups_ok else 'FAIL'}")
        print(f"✅ Box score collection: {'PASS' if box_scores_ok else 'FAIL'}")
        print(f"✅ Prediction generation: {'PASS' if predictions_ok else 'FAIL'}")
        
        if lineups_ok and box_scores_ok and predictions_ok:
            print("\n🎉 All tests passed!")
        else:
            print("\n⚠️  Some tests failed - check output above for details")
    finally:
        db.close()

if __name__ == "__main__":
    main()

