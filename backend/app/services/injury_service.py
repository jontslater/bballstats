"""
Injury Service

Manages injury data collection, updates, and queries.
"""
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional, List, Dict
from app.models.injury import Injury
from app.models.player import Player
from app.models.team import Team


class InjuryService:
    """Service for managing injuries."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_or_update_injury(
        self,
        player_id: int,
        status: str,
        injury_date: date,
        injury_type: Optional[str] = None,
        severity: Optional[str] = None,
        expected_return_date: Optional[date] = None,
        description: Optional[str] = None,
        source: Optional[str] = None
    ) -> Injury:
        """
        Create or update an injury record.
        
        Args:
            player_id: Player ID
            status: Injury status (Out, Doubtful, Questionable, Probable, Available)
            injury_date: Date of injury
            injury_type: Type of injury (ankle, knee, etc.)
            severity: Severity (minor, moderate, severe)
            expected_return_date: Expected return date
            description: Description of injury
            source: Source of information
        
        Returns:
            Injury object
        """
        # Check for existing active injury
        existing = self.db.query(Injury).filter(
            and_(
                Injury.player_id == player_id,
                Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
                Injury.actual_return_date.is_(None)
            )
        ).first()
        
        if existing:
            # Update existing injury
            existing.status = status
            existing.injury_type = injury_type or existing.injury_type
            existing.severity = severity or existing.severity
            existing.expected_return_date = expected_return_date or existing.expected_return_date
            existing.description = description or existing.description
            existing.source = source or existing.source
            existing.updated_at = datetime.now()
            
            # If status is Available, set actual return date
            if status == 'Available' and not existing.actual_return_date:
                existing.actual_return_date = date.today()
            
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new injury
            injury = Injury(
                player_id=player_id,
                injury_date=injury_date,
                injury_type=injury_type,
                status=status,
                severity=severity,
                expected_return_date=expected_return_date,
                description=description,
                source=source or 'manual'
            )
            
            self.db.add(injury)
            self.db.commit()
            self.db.refresh(injury)
            return injury
    
    def get_active_injuries(self, team_id: Optional[int] = None) -> List[Injury]:
        """
        Get all active injuries.
        
        Args:
            team_id: Optional team ID to filter by
        
        Returns:
            List of active injuries
        """
        query = self.db.query(Injury).filter(
            and_(
                Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
                Injury.actual_return_date.is_(None)
            )
        )
        
        if team_id:
            query = query.join(Player).filter(Player.current_team_id == team_id)
        
        return query.all()
    
    def get_team_injuries(self, team_id: int) -> List[Injury]:
        """
        Get all active injuries for a team.
        
        Args:
            team_id: Team ID
        
        Returns:
            List of injuries for players on this team
        """
        return self.db.query(Injury).join(Player).filter(
            and_(
                Player.current_team_id == team_id,
                Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
                Injury.actual_return_date.is_(None)
            )
        ).all()
    
    def get_player_injury(self, player_id: int) -> Optional[Injury]:
        """
        Get current injury for a player.
        
        Args:
            player_id: Player ID
        
        Returns:
            Active injury or None
        """
        return self.db.query(Injury).filter(
            and_(
                Injury.player_id == player_id,
                Injury.status.in_(['Out', 'Doubtful', 'Questionable', 'Probable']),
                Injury.actual_return_date.is_(None)
            )
        ).first()
    
    def mark_injury_resolved(self, injury_id: int, actual_return_date: Optional[date] = None) -> Injury:
        """
        Mark an injury as resolved.
        
        Args:
            injury_id: Injury ID
            actual_return_date: Actual return date (default: today)
        
        Returns:
            Updated injury
        """
        injury = self.db.query(Injury).filter(Injury.injury_id == injury_id).first()
        if not injury:
            raise ValueError(f"Injury {injury_id} not found")
        
        injury.status = 'Available'
        injury.actual_return_date = actual_return_date or date.today()
        injury.updated_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(injury)
        return injury


