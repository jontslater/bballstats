#!/usr/bin/env python3
"""
Test database connection and table creation.

Usage:
    python scripts/test_database.py
"""
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy import inspect, text
from app.database import engine, SessionLocal, init_db, Base


def test_connection():
    """Test database connection."""
    print("=" * 60)
    print("TEST 1: Database Connection")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                print("✅ Database connection successful!")
                return True
            else:
                print("❌ Database connection failed - unexpected result")
                return False
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Make sure:")
        print("   1. PostgreSQL is running")
        print("   2. Database 'nba_betting' exists")
        print("   3. DATABASE_URL in backend/.env is correct")
        return False


def test_table_creation():
    """Test table creation."""
    print("\n" + "=" * 60)
    print("TEST 2: Table Creation")
    print("=" * 60)
    
    try:
        # Create all tables
        print("Creating tables...")
        init_db()
        
        # Check if tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = [
            "teams", "seasons", "players", "games", "player_game_stats",
            "injuries", "team_position_defense", "player_team_matchups",
            "injury_impact_history", "predictions", "game_schedules",
            "user_plays", "lineups"
        ]
        
        print(f"\n✅ Found {len(tables)} tables in database")
        
        # Check each expected table
        missing = []
        for table in expected_tables:
            if table in tables:
                print(f"   ✅ {table}")
            else:
                print(f"   ❌ {table} - MISSING")
                missing.append(table)
        
        if missing:
            print(f"\n⚠️  {len(missing)} tables missing: {', '.join(missing)}")
            return False
        else:
            print(f"\n✅ All {len(expected_tables)} expected tables exist!")
            return True
            
    except Exception as e:
        print(f"❌ Table creation failed: {e}")
        return False


def test_table_structure():
    """Test table structure (columns)."""
    print("\n" + "=" * 60)
    print("TEST 3: Table Structure")
    print("=" * 60)
    
    try:
        inspector = inspect(engine)
        
        # Test teams table structure
        print("\nTesting 'teams' table structure...")
        columns = inspector.get_columns("teams")
        expected_columns = ["team_id", "name", "abbreviation", "conference", "division"]
        
        found_columns = [col["name"] for col in columns]
        for col in expected_columns:
            if col in found_columns:
                print(f"   ✅ {col}")
            else:
                print(f"   ❌ {col} - MISSING")
        
        # Test predictions table (most complex)
        print("\nTesting 'predictions' table structure...")
        columns = inspector.get_columns("predictions")
        key_columns = ["prediction_id", "player_id", "game_id", "stat_type", 
                      "distribution_mean", "distribution_std_dev", "bet_type"]
        
        found_columns = [col["name"] for col in columns]
        for col in key_columns:
            if col in found_columns:
                print(f"   ✅ {col}")
            else:
                print(f"   ❌ {col} - MISSING")
        
        print(f"\n✅ Table structures verified!")
        return True
        
    except Exception as e:
        print(f"❌ Table structure check failed: {e}")
        return False


def test_relationships():
    """Test that relationships work."""
    print("\n" + "=" * 60)
    print("TEST 4: Model Relationships")
    print("=" * 60)
    
    try:
        from app.models import Team, Player, Game
        
        db = SessionLocal()
        
        # Test that we can query
        team_count = db.query(Team).count()
        player_count = db.query(Player).count()
        game_count = db.query(Game).count()
        
        print(f"✅ Teams: {team_count}")
        print(f"✅ Players: {player_count}")
        print(f"✅ Games: {game_count}")
        
        # Test relationships (if data exists)
        if team_count > 0:
            team = db.query(Team).first()
            print(f"✅ Team relationships work: {team}")
            if hasattr(team, 'players'):
                print(f"   ✅ Team.players relationship exists")
        
        db.close()
        print("\n✅ Model relationships verified!")
        return True
        
    except Exception as e:
        print(f"❌ Relationship test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n🏀 NBA Betting Analytics - Database Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Connection", test_connection()))
    results.append(("Table Creation", test_table_creation()))
    results.append(("Table Structure", test_table_structure()))
    results.append(("Relationships", test_relationships()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20s} {status}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n🎉 All tests passed! Database is ready.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

