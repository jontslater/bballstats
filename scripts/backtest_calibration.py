#!/usr/bin/env python3
"""
Walk-forward backtest of calibrated probabilities.

For each past MLB game date with enough history, uses only games before that date
to compute calibrated probabilities, then compares with actual outcomes.

Usage:
    DATABASE_URL=postgresql://... python scripts/backtest_calibration.py
"""
import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import json

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import only what we need to avoid heavy dependencies
import importlib.util

def load_module(module_name, file_path):
    """Load a module from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load calibrated probability calculator
calibrated_prob = load_module(
    'calibrated_probability',
    backend_path / 'app' / 'services' / 'calibrated_probability.py'
)
CalibratedProbabilityCalculator = calibrated_prob.CalibratedProbabilityCalculator

from sqlalchemy import create_engine, func, and_, or_
from sqlalchemy.orm import sessionmaker
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game


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


def compute_brier_score(predictions: List[Tuple[float, int]]) -> float:
    """
    Compute Brier score for probabilistic predictions.
    
    Args:
        predictions: List of (predicted_prob, actual_outcome) tuples
                    where actual_outcome is 0 or 1
    
    Returns:
        Brier score (lower is better, 0 = perfect)
    """
    if not predictions:
        return 0.0
    
    total_error = sum((pred - actual) ** 2 for pred, actual in predictions)
    return total_error / len(predictions)


def walk_forward_backtest(db, min_history_games: int = 10, max_test_dates: int = 50):
    """
    Walk-forward backtest on historical MLB game data.
    
    For each test date:
    1. Get players with >= min_history_games before test date
    2. Compute calibrated probability using only pre-test-date data
    3. Compare predicted probability with actual outcome on test date
    
    Args:
        db: SQLAlchemy session
        min_history_games: Minimum games needed to make prediction
        max_test_dates: Maximum number of test dates to evaluate
    
    Returns:
        Dict with results per stat type
    """
    print("=" * 80)
    print("WALK-FORWARD CALIBRATION BACKTEST")
    print("=" * 80)
    print()
    
    # Get all MLB game dates with stats
    game_dates = db.query(Game.game_date).filter(
        Game.sport == 'MLB',
        Game.game_status == 'final'
    ).distinct().order_by(Game.game_date.desc()).limit(max_test_dates).all()
    
    if not game_dates:
        print("⚠️  No completed MLB games found in database.")
        return None
    
    game_dates = [gd[0] for gd in game_dates]
    print(f"Found {len(game_dates)} test dates from {min(game_dates)} to {max(game_dates)}")
    print()
    
    # Initialize result trackers per stat
    stats_to_test = ['hits', 'total_bases', 'home_runs']
    results = {
        stat: {
            'buckets': defaultdict(lambda: {'total': 0, 'hits': 0, 'sum_prob': 0.0}),
            'predictions': []  # For Brier score
        }
        for stat in stats_to_test
    }
    
    # League averages (computed once from all data)
    league_stats = {}
    for stat in stats_to_test:
        stat_col = getattr(PlayerGameStat, stat)
        avg = db.query(func.avg(stat_col)).filter(
            PlayerGameStat.sport == 'MLB',
            stat_col.isnot(None),
            stat_col >= 0
        ).scalar()
        std = db.query(func.stddev(stat_col)).filter(
            PlayerGameStat.sport == 'MLB',
            stat_col.isnot(None),
            stat_col >= 0
        ).scalar()
        league_stats[stat] = {'mean': avg or 0.0, 'std': std or 1.0}
        print(f"League average {stat}: mean={avg:.2f}, std={std:.2f}")
    
    print()
    print(f"Running walk-forward test on {len(game_dates)} dates...")
    print()
    
    calc = CalibratedProbabilityCalculator(sport='MLB')
    total_predictions = 0
    
    for test_date in game_dates:
        # Get games on test date
        test_games = db.query(Game).filter(
            Game.sport == 'MLB',
            Game.game_date == test_date,
            Game.game_status == 'final'
        ).all()
        
        if not test_games:
            continue
        
        # Get actual stats on test date
        test_stats = db.query(PlayerGameStat).filter(
            PlayerGameStat.sport == 'MLB',
            PlayerGameStat.game_id.in_([g.game_id for g in test_games])
        ).all()
        
        for stat_row in test_stats:
            player_id = stat_row.player_id
            
            # Get historical stats BEFORE test date (no lookahead)
            history = db.query(PlayerGameStat).join(Game).filter(
                PlayerGameStat.sport == 'MLB',
                PlayerGameStat.player_id == player_id,
                Game.game_date < test_date,
                Game.game_status == 'final'
            ).order_by(Game.game_date.desc()).limit(50).all()
            
            if len(history) < min_history_games:
                continue
            
            # For each stat, compute calibrated probability and compare
            for stat in stats_to_test:
                actual_value = getattr(stat_row, stat)
                if actual_value is None:
                    continue
                
                # Compute player stats from history
                stat_values = [getattr(h, stat) for h in history if getattr(h, stat) is not None]
                if len(stat_values) < min_history_games:
                    continue
                
                import statistics
                player_mean = statistics.mean(stat_values)
                player_std = statistics.stdev(stat_values) if len(stat_values) > 1 else 1.0
                sample_size = len(stat_values)
                
                # Test lines: OVER 0.5, 1.5, 2.5
                test_lines = [0.5, 1.5]
                if stat == 'home_runs':
                    test_lines = [0.5]  # Only test OVER 0.5 for HRs
                
                for line in test_lines:
                    # Compute calibrated probability
                    prob_data = calc.calculate_probability_for_line(
                        line=line,
                        player_mean=player_mean,
                        player_std=player_std,
                        sample_size=sample_size,
                        stat_type=stat,
                        league_mean=league_stats[stat]['mean'],
                        league_std=league_stats[stat]['std']
                    )
                    
                    predicted_prob = prob_data['probability']
                    actual_hit = 1 if actual_value > line else 0
                    
                    # Record result
                    bucket = bucket_probability(predicted_prob)
                    results[stat]['buckets'][bucket]['total'] += 1
                    results[stat]['buckets'][bucket]['hits'] += actual_hit
                    results[stat]['buckets'][bucket]['sum_prob'] += predicted_prob
                    results[stat]['predictions'].append((predicted_prob, actual_hit))
                    
                    total_predictions += 1
    
    print(f"✓ Completed {total_predictions} predictions across {len(game_dates)} test dates")
    print()
    
    return results, league_stats


def print_reliability_table(results: Dict, league_stats: Dict):
    """Print reliability table per stat and overall."""
    
    all_buckets = [
        "0.00-0.49", "0.50-0.54", "0.55-0.59", "0.60-0.64", "0.65-0.69",
        "0.70-0.74", "0.75-0.79", "0.80-0.84", "0.85-0.89", "0.90-1.00"
    ]
    
    for stat in results.keys():
        buckets = results[stat]['buckets']
        predictions = results[stat]['predictions']
        
        print("=" * 80)
        print(f"STAT: {stat.upper()}")
        print("=" * 80)
        print()
        print("Probability Bucket | Count | Predicted | Actual | Calibration Error")
        print("-" * 80)
        
        total_preds = 0
        total_hits = 0
        total_pred_prob = 0.0
        
        for bucket in all_buckets:
            if bucket not in buckets or buckets[bucket]['total'] == 0:
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
            
            error = actual_rate - avg_pred_prob
            error_str = f"{error:+.1%}"
            
            print(f"{bucket:18} | {count:5} | {avg_pred_prob:8.1%} | {actual_rate:6.1%} | {error_str}")
        
        print("-" * 80)
        if total_preds > 0:
            overall_pred = total_pred_prob / total_preds
            overall_actual = total_hits / total_preds
            overall_error = overall_actual - overall_pred
            
            print(f"{'OVERALL':18} | {total_preds:5} | {overall_pred:8.1%} | {overall_actual:6.1%} | {overall_error:+.1%}")
            
            # Brier score
            if predictions:
                brier = compute_brier_score(predictions)
                
                # Baseline: always predict league average
                league_avg = league_stats[stat]['mean']
                # For OVER 0.5, baseline is P(stat >= 1)
                # Approximate with league mean (if mean is 1.0, P(>=1) ~ 0.5-0.6)
                baseline_prob = min(0.90, max(0.10, league_avg / (league_avg + 0.5)))
                baseline_predictions = [(baseline_prob, actual) for _, actual in predictions]
                baseline_brier = compute_brier_score(baseline_predictions)
                
                improvement = ((baseline_brier - brier) / baseline_brier) * 100 if baseline_brier > 0 else 0
                
                print()
                print(f"Brier Score: {brier:.4f}")
                print(f"Baseline (league rate): {baseline_brier:.4f}")
                print(f"Improvement: {improvement:+.1f}%")
        
        print()
        print()


def main():
    """Run walk-forward calibration backtest."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        print()
        print("Usage:")
        print("  DATABASE_URL=postgresql://user:pass@host/db python scripts/backtest_calibration.py")
        sys.exit(1)
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        results, league_stats = walk_forward_backtest(db, min_history_games=10, max_test_dates=50)
        
        if results is None:
            sys.exit(1)
        
        print_reliability_table(results, league_stats)
        
        print("=" * 80)
        print("INTERPRETATION")
        print("=" * 80)
        print()
        print("Calibration Error:")
        print("  • Well-calibrated: Actual rate ≈ Predicted probability (error near 0%)")
        print("  • Under-confident: Actual rate > Predicted (positive error)")
        print("  • Over-confident: Actual rate < Predicted (negative error)")
        print()
        print("Brier Score:")
        print("  • Lower is better (0 = perfect, 0.25 = random)")
        print("  • Compare to baseline (always predict league average)")
        print()
        print("RECOMMENDATIONS:")
        print("  • If home_runs OVER 0.5 is over-confident (predicted ~50%, actual ~20%),")
        print("    increase shrinkage toward league base rate in calibrated_probability.py")
        print("  • Tune BASE_HIT_RATES per stat in CalibratedProbabilityCalculator")
        print("  • Check that base rate is P(stat >= line), not mean count")
        print()
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
