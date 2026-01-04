#!/usr/bin/env python3
"""
Analyze historical injury impacts.

Usage:
    python scripts/analyze_injury_impacts.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.database import SessionLocal
from app.services.injury_impact_analyzer import InjuryImpactAnalyzer

if __name__ == "__main__":
    print("🏥 Analyzing Historical Injury Impacts...")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        analyzer = InjuryImpactAnalyzer(db)
        
        print("Analyzing historical injury patterns...")
        print("This may take a few minutes...")
        print()
        
        results = analyzer.analyze_historical_impacts()
        
        print("=" * 60)
        print("✅ COMPLETE")
        print("=" * 60)
        print(f"Injuries analyzed: {results['injuries_analyzed']}")
        print(f"Impact records created: {results['impact_records_created']}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


