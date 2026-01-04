#!/usr/bin/env python3
"""
Recalculate all analytics.

Usage:
    python scripts/recalculate_analytics.py [--season-id SEASON_ID]
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.analytics_service import AnalyticsService

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Recalculate all analytics')
    parser.add_argument('--season-id', type=int, default=None,
                       help='Season ID (default: current season)')
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        service = AnalyticsService(db)
        results = service.recalculate_all(season_id=args.season_id)
        
        print("\n📊 Summary:")
        print(f"   Team Defense: {results.get('team_defense', {}).get('created', 0) + results.get('team_defense', {}).get('updated', 0)} records")
        print(f"   Matchups: {results.get('matchups', {}).get('created', 0) + results.get('matchups', {}).get('updated', 0)} records")
        print(f"   Pace: {results.get('pace', {}).get('teams_calculated', 0)} teams")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


