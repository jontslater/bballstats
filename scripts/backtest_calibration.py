#!/usr/bin/env python3
"""
Backtest calibration of predicted probabilities.

Compares predicted probability buckets to actual hit rates for resolved
MLB predictions in the database.

Usage:
    PYTHONPATH=backend python scripts/backtest_calibration.py
"""
import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker
from app.core.database import get_db_url
from app.models.prediction import Prediction


def bucket_probability(prob: float) -> str:
    """Bucket probability into ranges."""
    if prob < 0.50:
        return "0.00-0.49"
    elif prob < 0.55:
        return "0.50-0.54"
    elif prob < 0.60:
        return "0.55-0.59"
    elif prob < 0.65:
        return "0.60-0.64"
    elif prob < 0.70:
        return "0.65-0.69"
    elif prob < 0.75:
        return "0.70-0.74"
    elif prob < 0.80:
        return "0.75-0.79"
    elif prob < 0.85:
        return "0.80-0.84"
    elif prob < 0.90:
        return "0.85-0.89"
    else:
        return "0.90-1.00"


def backtest_calibration():
    """Run calibration backtest on resolved predictions."""
    print("=" * 80)
    print("CALIBRATION BACKTEST: Predicted Probability vs Actual Hit Rate")
    print("=" * 80)
    print()
    
    # Connect to database
    db_url = get_db_url()
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Query resolved predictions
        # A prediction is resolved if actual_value is not None
        resolved = db.query(Prediction).filter(
            Prediction.actual_value.isnot(None),
            Prediction.predicted_probability.isnot(None),
            Prediction.line.isnot(None),
            Prediction.sport == 'MLB'  # Start with MLB
        ).all()
        
        if not resolved:
            print("⚠️  No resolved MLB predictions found in database.")
            print("    Cannot perform calibration backtest without historical results.")
            print()
            print("    To collect data:")
            print("    1. Generate predictions for upcoming games")
            print("    2. Wait for games to complete")
            print("    3. Update predictions with actual_value")
            print("    4. Re-run this backtest script")
            return
        
        print(f"Found {len(resolved)} resolved MLB predictions")
        print()
        
        # Bucket predictions and calculate hit rates
        buckets = defaultdict(lambda: {'total': 0, 'hits': 0, 'sum_prob': 0.0})
        
        for pred in resolved:
            prob = pred.predicted_probability
            line = pred.line
            actual = pred.actual_value
            
            # Determine if prediction "hit" (actual value exceeded line)
            hit = 1 if actual > line else 0
            
            bucket = bucket_probability(prob)
            buckets[bucket]['total'] += 1
            buckets[bucket]['hits'] += hit
            buckets[bucket]['sum_prob'] += prob
        
        # Print reliability table
        print("Probability Bucket | Count | Predicted | Actual | Calibration")
        print("-" * 80)
        
        all_buckets = [
            "0.00-0.49", "0.50-0.54", "0.55-0.59", "0.60-0.64", "0.65-0.69",
            "0.70-0.74", "0.75-0.79", "0.80-0.84", "0.85-0.89", "0.90-1.00"
        ]
        
        total_preds = 0
        total_hits = 0
        total_pred_prob = 0.0
        
        for bucket in all_buckets:
            if bucket not in buckets:
                print(f"{bucket:18} | {0:5} | {'-':9} | {'-':6} | -")
                continue
            
            data = buckets[bucket]
            count = data['total']
            hits = data['hits']
            avg_pred_prob = data['sum_prob'] / count
            actual_rate = hits / count
            
            total_preds += count
            total_hits += hits
            total_pred_prob += data['sum_prob']
            
            # Calibration error
            error = actual_rate - avg_pred_prob
            error_str = f"{error:+.1%}"
            
            print(f"{bucket:18} | {count:5} | {avg_pred_prob:8.1%} | {actual_rate:6.1%} | {error_str}")
        
        print("-" * 80)
        overall_pred = total_pred_prob / total_preds if total_preds > 0 else 0
        overall_actual = total_hits / total_preds if total_preds > 0 else 0
        overall_error = overall_actual - overall_pred
        
        print(f"{'OVERALL':18} | {total_preds:5} | {overall_pred:8.1%} | {overall_actual:6.1%} | {overall_error:+.1%}")
        print()
        
        # Interpretation
        print("INTERPRETATION:")
        print("  • Well-calibrated: Actual rate ≈ Predicted probability (error near 0%)")
        print("  • Under-confident: Actual rate > Predicted (positive error)")
        print("  • Over-confident: Actual rate < Predicted (negative error)")
        print()
        
        if abs(overall_error) < 0.03:
            print("✅ Overall calibration is good (error < 3%)")
        elif overall_error > 0.05:
            print("⚠️  Predictions are under-confident (can increase probabilities)")
        elif overall_error < -0.05:
            print("⚠️  Predictions are over-confident (should decrease probabilities)")
        else:
            print("✓  Overall calibration is reasonable (error 3-5%)")
        
        print()
        print("RECOMMENDATIONS:")
        print("  • If buckets have < 20 samples, results may not be reliable")
        print("  • Tune base_rate weights in calibrated_probability.py if overall error > 5%")
        print("  • Check sport-specific BASE_HIT_RATES if certain stats are off")
        
    finally:
        db.close()


if __name__ == '__main__':
    backtest_calibration()
