"""
Database configuration and connection setup.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
# Default uses Mac username (no password needed for local connection)
import getpass
default_user = getpass.getuser()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{default_user}@localhost:5432/nba_betting"
)

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    echo=False  # Set to True for SQL query logging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session.
    Use this in FastAPI route dependencies.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables.
    Call this after defining all models.
    """
    # Import all models to register them with Base
    from app.models import (Team, Season, Player, Game, PlayerGameStat,
                           Injury, TeamPositionDefense, PlayerTeamMatchup,
                           InjuryImpactHistory, Prediction, GameSchedule,
                           UserPlay, Lineup, PoorMansBetChallenge, PoorMansBetDay, ValueLadder,
                           HistoricalSuggestedBet, HistoricalParlay, HistoricalParlayLeg)
    
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

