"""
Injury Context Service

Provides context about current injuries and their impact on predictions.
"""
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from app.services.injury_service import InjuryService
from app.services.injury_impact_analyzer import InjuryImpactAnalyzer
from app.models.player import Player
from app.models.team import Team


class InjuryContext:
    """Provide injury context for predictions."""
    
    def __init__(self, db: Session):
        self.db = db
        self.injury_service = InjuryService(db)
        self.impact_analyzer = InjuryImpactAnalyzer(db)
    
    def get_team_injury_context(self, team_id: int) -> Dict:
        """
        Get full injury context for a team.
        
        Returns:
            Dict with:
            - active_injuries: List of injured players
            - affected_positions: Positions with injuries
            - beneficiary_players: Players who benefit from injuries
            - expected_impacts: Expected stat increases for beneficiaries
        """
        # Get active injuries
        injuries = self.injury_service.get_team_injuries(team_id)
        
        active_injuries = []
        affected_positions = set()
        beneficiary_players = []
        expected_impacts = {}
        
        for injury in injuries:
            player = self.db.query(Player).filter(
                Player.player_id == injury.player_id
            ).first()
            
            if not player:
                continue
            
            active_injuries.append({
                "player_id": player.player_id,
                "player_name": player.name,
                "position": player.position,
                "status": injury.status,
                "injury_type": injury.injury_type
            })
            
            if player.position:
                affected_positions.add(player.position)
            
            # Find beneficiaries
            if player.position and injury.status in ['Out', 'Doubtful']:
                backups = self._find_backup_players(team_id, player.position, player.player_id)
                
                for backup in backups:
                    if backup.player_id not in [b['player_id'] for b in beneficiary_players]:
                        beneficiary_players.append({
                            "player_id": backup.player_id,
                            "player_name": backup.name,
                            "position": backup.position
                        })
                    
                    # Get expected impact
                    impact = self.impact_analyzer.get_expected_impact(
                        injured_player_id=player.player_id,
                        beneficiary_player_id=backup.player_id
                    )
                    
                    if impact:
                        key = f"{backup.player_id}"
                        if key not in expected_impacts:
                            expected_impacts[key] = {
                                "player_id": backup.player_id,
                                "player_name": backup.name,
                                "impacts": []
                            }
                        
                        expected_impacts[key]["impacts"].append({
                            "injured_player_id": player.player_id,
                            "injured_player_name": player.name,
                            "minutes_increase": impact["avg_minutes_increase"],
                            "points_increase": impact["avg_points_increase"],
                            "rebounds_increase": impact["avg_rebounds_increase"],
                            "assists_increase": impact["avg_assists_increase"],
                            "games_analyzed": impact["games_analyzed"]
                        })
        
        return {
            "team_id": team_id,
            "active_injuries": active_injuries,
            "affected_positions": list(affected_positions),
            "beneficiary_players": beneficiary_players,
            "expected_impacts": list(expected_impacts.values())
        }
    
    def get_player_injury_status(self, player_id: int) -> Optional[Dict]:
        """
        Get injury status for a specific player.
        
        Returns:
            Dict with injury info or None if no active injury
        """
        injury = self.injury_service.get_player_injury(player_id)
        
        if not injury:
            return None
        
        player = self.db.query(Player).filter(Player.player_id == player_id).first()
        
        return {
            "player_id": player_id,
            "player_name": player.name if player else None,
            "status": injury.status,
            "injury_type": injury.injury_type,
            "injury_date": injury.injury_date.isoformat() if injury.injury_date else None,
            "expected_return_date": injury.expected_return_date.isoformat() if injury.expected_return_date else None,
            "description": injury.description
        }
    
    def _find_backup_players(self, team_id: int, position: str, exclude_player_id: int) -> List[Player]:
        """Find backup players at the same position."""
        return self.db.query(Player).filter(
            and_(
                Player.current_team_id == team_id,
                Player.position == position,
                Player.player_id != exclude_player_id
            )
        ).all()


