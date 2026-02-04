#!/usr/bin/env python3
"""
Generate test NFL games for the current week to test NFL predictions.

This creates mock NFL games for the next 7 days to allow testing of the NFL prediction system.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import random

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Game, Team, Season


def generate_test_nfl_games():
    """Generate test NFL games for the next week."""
    print("🏈 Generating test NFL games...")
    print("=" * 60)

    db = SessionLocal()
    try:
        # Get NFL season
        season = db.query(Season).filter(
            Season.sport == 'NFL',
            Season.is_current == True
        ).first()

        if not season:
            print("❌ No current NFL season found")
            return

        print(f"Using NFL season: {season.season_year}")

        # Get all NFL teams
        nfl_teams = db.query(Team).filter(Team.sport == 'NFL').all()
        if len(nfl_teams) < 10:
            print(f"❌ Not enough NFL teams: {len(nfl_teams)}")
            return

        print(f"Found {len(nfl_teams)} NFL teams")

        # Create specific real NFL games for today and tomorrow
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # Real NFL games provided by user
        real_games = [
            # Today (2026-01-17)
            {'date': today, 'away': 'DEN', 'home': 'BUF', 'time': '15:30'},  # Broncos vs Bills at 3:30 PM CST
            {'date': today, 'away': 'SF', 'home': 'SEA', 'time': '19:00'},   # 49ers vs Seahawks at 7:00 PM

            # Tomorrow (2026-01-18)
            {'date': tomorrow, 'away': 'HOU', 'home': 'NE', 'time': '14:00'},  # Texans vs Patriots at 2:00 PM
            {'date': tomorrow, 'away': 'LAR', 'home': 'CHI', 'time': '17:30'}, # Rams vs Bears at 5:30 PM
        ]

        games_created = 0

        for game_info in real_games:
            # Find teams by abbreviation
            away_team = next((t for t in nfl_teams if t.abbreviation == game_info['away']), None)
            home_team = next((t for t in nfl_teams if t.abbreviation == game_info['home']), None)

            if not away_team or not home_team:
                print(f"❌ Could not find teams: {game_info['away']} @ {game_info['home']}")
                continue

            # Check if game already exists
            existing_game = db.query(Game).filter(
                Game.sport == 'NFL',
                Game.game_date == game_info['date'],
                Game.home_team_id == home_team.team_id,
                Game.away_team_id == away_team.team_id
            ).first()

            if existing_game:
                print(f"ℹ️ Game already exists: {game_info['away']} @ {game_info['home']} on {game_info['date']}")
                continue

            # Create new game
            game = Game(
                sport='NFL',
                game_date=game_info['date'],
                season_id=season.season_id,
                home_team_id=home_team.team_id,
                away_team_id=away_team.team_id,
                game_status='scheduled'
            )

            db.add(game)
            games_created += 1
            print(f"✅ Created: {game_info['away']} @ {game_info['home']} on {game_info['date']} at {game_info['time']}")

        # Also create a few additional random games for more testing
        print("\n📝 Adding additional test games...")
        for day_offset in range(2, 5):  # Days 2-4 from today
            game_date = today + timedelta(days=day_offset)
            num_games = random.randint(1, 2)

            # Shuffle teams for random matchups
            available_teams = [t for t in nfl_teams if t.abbreviation not in ['DEN', 'BUF', 'SF', 'SEA', 'HOU', 'NE', 'LAR', 'CHI']]
            random.shuffle(available_teams)

            for i in range(0, min(len(available_teams) - 1, num_games * 2), 2):
                home_team = available_teams[i]
                away_team = available_teams[i + 1]

                # Check if game already exists
                existing_game = db.query(Game).filter(
                    Game.sport == 'NFL',
                    Game.game_date == game_date,
                    Game.home_team_id == home_team.team_id,
                    Game.away_team_id == away_team.team_id
                ).first()

                if existing_game:
                    continue

                # Create new game
                game = Game(
                    sport='NFL',
                    game_date=game_date,
                    season_id=season.season_id,
                    home_team_id=home_team.team_id,
                    away_team_id=away_team.team_id,
                    game_status='scheduled'
                )

                db.add(game)
                games_created += 1

        db.commit()
        print("=" * 60)
        print("✅ SUMMARY")
        print("=" * 60)
        print(f"✅ Created: {games_created} test NFL games")
        print(f"📅 Date range: {today} to {today + timedelta(days=6)}")

        # Show sample games
        sample_games = db.query(Game).filter(
            Game.sport == 'NFL',
            Game.game_date >= today,
            Game.game_date <= today + timedelta(days=6)
        ).limit(5).all()

        print("\n📋 Sample games created:")
        for game in sample_games:
            print(f"  {game.away_team.abbreviation} @ {game.home_team.abbreviation} - {game.game_date}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    generate_test_nfl_games()
    print("\n🎉 Test NFL games generated!")
    print("💡 Now you can run NFL predictions and test the full NFL system.")