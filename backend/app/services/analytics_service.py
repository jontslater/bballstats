"""
Analytics Service

Master service that coordinates all analytics calculations.
"""
from sqlalchemy.orm import Session
from typing import Optional
from app.services.team_defense_calculator import TeamDefenseCalculator
from app.services.matchup_analyzer import MatchupAnalyzer
from app.services.pace_calculator import PaceCalculator


class AnalyticsService:
    """Master service for all analytics calculations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.team_defense = TeamDefenseCalculator(db)
        self.matchup_analyzer = MatchupAnalyzer(db)
        self.pace_calculator = PaceCalculator(db)
    
    def recalculate_all(self, season_id: Optional[int] = None) -> dict:
        """
        Recalculate all analytics.
        
        Returns:
            Dict with summary of what was calculated
        """
        results = {
            "team_defense": {},
            "matchups": {},
            "pace": {}
        }
        
        print("🔄 Recalculating all analytics...")
        print("=" * 60)
        
        # 1. Team Position Defense
        print("\n1️⃣  Calculating team position defense...")
        try:
            results["team_defense"] = self.team_defense.calculate_all_teams_positions(season_id)
            print(f"   ✅ Team defense: {results['team_defense']['created'] + results['team_defense']['updated']} records")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results["team_defense"]["error"] = str(e)
        
        # 2. Player-Team Matchups
        print("\n2️⃣  Calculating player-team matchups...")
        try:
            results["matchups"] = self.matchup_analyzer.calculate_all_matchups(season_id)
            print(f"   ✅ Matchups: {results['matchups']['created'] + results['matchups']['updated']} records")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results["matchups"]["error"] = str(e)
        
        # 3. Team Paces (update team_position_defense with pace)
        print("\n3️⃣  Calculating team paces...")
        try:
            paces = self.pace_calculator.calculate_all_team_paces(season_id)
            print(f"   ✅ Pace: {len(paces)} teams calculated")
            results["pace"]["teams_calculated"] = len(paces)
            
            # Update team_position_defense records with pace
            # (This would require updating the defense calculator to include pace)
            # For now, we'll just calculate and return
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results["pace"]["error"] = str(e)
        
        print("\n" + "=" * 60)
        print("✅ Analytics recalculation complete!")
        print("=" * 60)
        
        return results





