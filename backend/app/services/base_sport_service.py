"""
Base Sport Service

Base class for sport-aware services. Provides common functionality
for services that need to handle multiple sports (NBA, NFL, etc.).
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.config.sport_config import get_sport_config, is_valid_stat_type, is_valid_position


class BaseSportService:
    """
    Base class for services that work with multiple sports.
    
    All services should inherit from this when they need to handle
    sport-specific logic.
    """
    
    def __init__(self, db: Session, sport: str = 'NBA'):
        """
        Initialize service with database session and sport.
        
        Args:
            db: Database session
            sport: Sport type ('NBA' or 'NFL'). Defaults to 'NBA' for backward compatibility.
        """
        self.db = db
        self.sport = sport
        self.config = get_sport_config(sport)
    
    def get_stat_types(self) -> list:
        """Get list of stat types for this sport."""
        return self.config['stat_types']
    
    def get_positions(self) -> list:
        """Get list of positions for this sport."""
        return self.config['positions']
    
    def get_default_stat_type(self, position: Optional[str] = None) -> str:
        """Get default stat type for this sport, optionally for a position."""
        from app.config.sport_config import get_default_stat_type
        return get_default_stat_type(self.sport, position)
    
    def get_stat_type_label(self, stat_type: str) -> str:
        """Get human-readable label for a stat type."""
        from app.config.sport_config import get_stat_type_label
        return get_stat_type_label(self.sport, stat_type)
    
    def is_valid_stat_type(self, stat_type: str) -> bool:
        """Check if a stat type is valid for this sport."""
        return is_valid_stat_type(self.sport, stat_type)
    
    def is_valid_position(self, position: str) -> bool:
        """Check if a position is valid for this sport."""
        return is_valid_position(self.sport, position)
    
    def get_time_unit(self) -> str:
        """Get the time unit for this sport (minutes_played or snaps_played)."""
        return self.config['time_unit']
    
    def validate_stat_type(self, stat_type: str) -> None:
        """Validate stat type and raise error if invalid."""
        if not self.is_valid_stat_type(stat_type):
            raise ValueError(
                f"Invalid stat type '{stat_type}' for sport '{self.sport}'. "
                f"Valid types: {self.get_stat_types()}"
            )
    
    def validate_position(self, position: str) -> None:
        """Validate position and raise error if invalid."""
        if not self.is_valid_position(position):
            raise ValueError(
                f"Invalid position '{position}' for sport '{self.sport}'. "
                f"Valid positions: {self.get_positions()}"
            )

