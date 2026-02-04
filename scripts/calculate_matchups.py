#!/usr/bin/env python3
"""
Calculate player-team matchup stats.

Usage:
    python scripts/calculate_matchups.py [--season-id SEASON_ID]
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.matchup_analyzer import MatchupAnalyzer

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Calculate player-team matchups')
    parser.add_argument('--season-id', type=int, default=None,
                       help='Season ID (default: current season)')
    
    args = parser.parse_args()
    
    print("🏀 Calculating Player-Team Matchups...")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        analyzer = MatchupAnalyzer(db)
        
        print("Calculating matchups for all players vs all teams...")
        print("This may take a few minutes...")
        print()
        
        results = analyzer.calculate_all_matchups(season_id=args.season_id)
        
        print("=" * 60)
        print("✅ COMPLETE")
        print("=" * 60)
        print(f"Records created: {results['created']}")
        print(f"Records updated: {results['updated']}")
        print(f"Total: {results['created'] + results['updated']}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()





