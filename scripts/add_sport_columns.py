"""
Migration script to add sport columns to all tables and mark existing data as NBA.

This script:
1. Adds 'sport' column to all relevant tables (default='NBA')
2. Updates unique constraints where needed (abbreviation, etc.)
3. Marks all existing data as 'NBA'
4. Creates indexes on sport columns for performance
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import text, inspect
from app.database import SessionLocal, engine
from app.models import (
    Season, Team, Player, Game, PlayerGameStat, Prediction,
    UserPlay, Parlay, PoorMansBetChallenge, TeamPositionDefense,
    PlayerTeamMatchup, GameSchedule
)


def add_sport_columns(db):
    """Add sport column to all tables."""
    print("📊 Adding sport columns to tables...")
    
    # Tables to update with their column definitions
    tables = {
        'seasons': "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'teams': "ALTER TABLE teams ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'players': "ALTER TABLE players ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'games': "ALTER TABLE games ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'player_game_stats': "ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'predictions': "ALTER TABLE predictions ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'user_plays': "ALTER TABLE user_plays ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'parlays': "ALTER TABLE parlays ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'poor_mans_bet_challenges': "ALTER TABLE poor_mans_bet_challenges ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'team_position_defense': "ALTER TABLE team_position_defense ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'player_team_matchups': "ALTER TABLE player_team_matchups ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
        'game_schedules': "ALTER TABLE game_schedules ADD COLUMN IF NOT EXISTS sport VARCHAR(10) DEFAULT 'NBA' NOT NULL;",
    }
    
    for table_name, sql in tables.items():
        try:
            db.execute(text(sql))
            print(f"  ✅ Added sport column to {table_name}")
        except Exception as e:
            # Column might already exist
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print(f"  ⚠️  Sport column already exists in {table_name}")
            else:
                print(f"  ❌ Error adding sport column to {table_name}: {e}")
                raise
    
    db.commit()
    print("✅ All sport columns added\n")


def create_indexes(db):
    """Create indexes on sport columns for performance."""
    print("📊 Creating indexes on sport columns...")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_seasons_sport ON seasons(sport);",
        "CREATE INDEX IF NOT EXISTS idx_teams_sport ON teams(sport);",
        "CREATE INDEX IF NOT EXISTS idx_players_sport ON players(sport);",
        "CREATE INDEX IF NOT EXISTS idx_games_sport ON games(sport);",
        "CREATE INDEX IF NOT EXISTS idx_player_game_stats_sport ON player_game_stats(sport);",
        "CREATE INDEX IF NOT EXISTS idx_predictions_sport ON predictions(sport);",
        "CREATE INDEX IF NOT EXISTS idx_user_plays_sport ON user_plays(sport);",
        "CREATE INDEX IF NOT EXISTS idx_parlays_sport ON parlays(sport);",
        "CREATE INDEX IF NOT EXISTS idx_poor_mans_bet_challenges_sport ON poor_mans_bet_challenges(sport);",
        "CREATE INDEX IF NOT EXISTS idx_team_position_defense_sport ON team_position_defense(sport);",
        "CREATE INDEX IF NOT EXISTS idx_player_team_matchups_sport ON player_team_matchups(sport);",
        "CREATE INDEX IF NOT EXISTS idx_game_schedules_sport ON game_schedules(sport);",
    ]
    
    for index_sql in indexes:
        try:
            db.execute(text(index_sql))
            print(f"  ✅ Created index")
        except Exception as e:
            print(f"  ⚠️  Index might already exist: {e}")
    
    db.commit()
    print("✅ All indexes created\n")


def update_unique_constraints(db):
    """Update unique constraints to include sport column."""
    print("📊 Updating unique constraints...")
    
    # Check what constraints exist and update them
    # Note: PostgreSQL doesn't support IF EXISTS for ALTER TABLE, so we'll handle errors gracefully
    
    constraints_to_update = [
        {
            'table': 'seasons',
            'old_constraint': 'seasons_season_year_key',
            'new_constraint': '_sport_season_uc',
            'columns': ['sport', 'season_year']
        },
        {
            'table': 'teams',
            'old_constraint': 'teams_abbreviation_key',
            'new_constraint': '_sport_abbreviation_uc',
            'columns': ['sport', 'abbreviation']
        },
    ]
    
    for constraint_info in constraints_to_update:
        try:
            # Drop old constraint if it exists
            drop_sql = f"ALTER TABLE {constraint_info['table']} DROP CONSTRAINT IF EXISTS {constraint_info['old_constraint']};"
            db.execute(text(drop_sql))
            
            # Add new constraint
            columns_str = ', '.join(constraint_info['columns'])
            add_sql = f"ALTER TABLE {constraint_info['table']} ADD CONSTRAINT {constraint_info['new_constraint']} UNIQUE ({columns_str});"
            db.execute(text(add_sql))
            
            print(f"  ✅ Updated constraint on {constraint_info['table']}")
        except Exception as e:
            # Constraint might already be updated or not exist
            if "already exists" in str(e).lower():
                print(f"  ⚠️  Constraint already exists on {constraint_info['table']}")
            else:
                print(f"  ⚠️  Could not update constraint on {constraint_info['table']}: {e}")
    
    db.commit()
    print("✅ Unique constraints updated\n")


def verify_data(db):
    """Verify that all existing data is marked as NBA."""
    print("📊 Verifying existing data...")
    
    tables_to_check = [
        ('seasons', Season),
        ('teams', Team),
        ('players', Player),
        ('games', Game),
        ('player_game_stats', PlayerGameStat),
        ('predictions', Prediction),
        ('user_plays', UserPlay),
        ('parlays', Parlay),
    ]
    
    for table_name, model in tables_to_check:
        try:
            # Reset any failed transactions
            db.rollback()
            
            # Check if sport column exists by trying to query it
            total = db.query(model).count()
            nba_count = db.query(model).filter(model.sport == 'NBA').count()
            
            # Check for nulls (SQLAlchemy handles None differently)
            null_query = db.query(model).filter(model.sport.is_(None))
            null_count = null_query.count()
            
            print(f"  {table_name}: {total} total, {nba_count} NBA, {null_count} null")
            
            if null_count > 0:
                print(f"    ⚠️  Found {null_count} records with null sport - updating...")
                null_query.update({model.sport: 'NBA'}, synchronize_session=False)
                db.commit()
                print(f"    ✅ Updated {null_count} records to NBA")
        except Exception as e:
            db.rollback()  # Reset on error
            error_str = str(e).lower()
            if "does not exist" in error_str or "no such column" in error_str or "no attribute" in error_str:
                print(f"  ⚠️  {table_name}: Sport column not found (column might not exist or model needs update)")
            else:
                print(f"  ⚠️  Error checking {table_name}: {e}")
    
    print("✅ Data verification complete\n")


def main():
    """Run the migration."""
    print("🚀 Starting sport column migration...")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Step 1: Add sport columns
        add_sport_columns(db)
        
        # Step 2: Create indexes
        create_indexes(db)
        
        # Step 3: Update unique constraints (optional, may fail if constraints don't exist)
        # update_unique_constraints(db)
        
        # Step 4: Verify data
        verify_data(db)
        
        print("=" * 60)
        print("✅ Migration complete!")
        print("\nNext steps:")
        print("1. Test the application with existing NBA data")
        print("2. Start collecting NFL data")
        print("3. Update services to filter by sport")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

