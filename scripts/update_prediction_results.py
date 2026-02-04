#!/usr/bin/env python3
"""
Update Prediction Results

Updates predictions with actual game results and calculates calibration statistics.
Run this after games finish to track prediction accuracy.

Usage:
    python scripts/update_prediction_results.py [--date YYYY-MM-DD]
    python scripts/update_prediction_results.py  # Updates all finished games
"""
import sys
from pathlib import Path
from datetime import date, datetime

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.services.prediction_calibration import PredictionCalibration


def update_results(game_date: date = None):
    """Update predictions with actual results."""
    db: Session = SessionLocal()
    try:
        calibration = PredictionCalibration(db)
        
        print("Updating predictions with actual results...")
        if game_date:
            print(f"Date: {game_date}")
        else:
            print("Updating all finished games without results...")
        
        result = calibration.update_predictions_with_results(game_date)
        
        print(f"\n✅ Update complete!")
        print(f"  Updated: {result['updated']}")
        print(f"  Skipped: {result['skipped']}")
        print(f"  Errors: {result['errors']}")
        print(f"  Total processed: {result['total']}")
        
        if result['updated'] > 0:
            print("\n📊 Calculating calibration statistics...")
            stats = calibration.get_calibration_stats()
            
            print("\nCalibration Statistics (Last 90 Days):")
            for bet_type in ['safe', 'standard', 'long_shot']:
                data = stats[bet_type]
                if data['total'] > 0:
                    hit_rate = data['hit_rate']
                    avg_prob = data['avg_prob']
                    diff = hit_rate - avg_prob
                    print(f"\n  {bet_type.upper()}:")
                    print(f"    Total: {data['total']}")
                    print(f"    Hit Rate: {hit_rate*100:.1f}%")
                    print(f"    Avg Predicted: {avg_prob*100:.1f}%")
                    # If actual < predicted (diff negative), we're OVER-confident (predicted too high)
                    # If actual > predicted (diff positive), we're UNDER-confident (predicted too low)
                    confidence_label = 'UNDER' if diff > 0 else 'OVER'
                    print(f"    Difference: {diff*100:+.1f}% ({confidence_label}-confident)")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def show_calibration_curves():
    """Show detailed calibration curves."""
    db: Session = SessionLocal()
    try:
        calibration = PredictionCalibration(db)
        
        print("📈 Calibration Curves (Last 90 Days):\n")
        curves = calibration.calculate_calibration_curves()
        
        for bet_type in ['safe', 'standard', 'long_shot']:
            if bet_type not in curves or not curves[bet_type]:
                continue
            
            print(f"\n{bet_type.upper()} BETS:")
            print("-" * 70)
            print(f"{'Range':<10} {'Sample':<8} {'Predicted':<10} {'Actual':<10} {'Adjust':<10}")
            print("-" * 70)
            
            for range_label, cal_data in sorted(curves[bet_type].items()):
                sample_size = cal_data['sample_size']
                pred_prob = cal_data['predicted_probability'] * 100
                actual_rate = cal_data['actual_hit_rate'] * 100
                adjustment = cal_data['calibration_adjustment'] * 100
                
                print(f"{range_label:<10} {sample_size:<8} {pred_prob:>6.1f}%   "
                      f"{actual_rate:>6.1f}%   {adjustment:>+6.1f}%")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Update predictions with actual results")
    parser.add_argument(
        "--date",
        type=str,
        help="Specific date to update (YYYY-MM-DD). If not provided, updates all finished games."
    )
    parser.add_argument(
        "--show-curves",
        action="store_true",
        help="Show calibration curves instead of updating results"
    )
    
    args = parser.parse_args()
    
    if args.show_curves:
        success = show_calibration_curves()
    else:
        game_date = None
        if args.date:
            try:
                game_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            except ValueError:
                print(f"❌ Invalid date format: {args.date}. Use YYYY-MM-DD")
                sys.exit(1)
        
        success = update_results(game_date)
    
    sys.exit(0 if success else 1)

