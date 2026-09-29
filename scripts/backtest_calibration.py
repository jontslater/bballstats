#!/usr/bin/env python3
"""
Walk-forward backtest of calibrated probabilities using discrete models.

For count stats (hits, home_runs, total_bases), uses Poisson/Negative Binomial
distribution with shrinkage toward league rate.

Usage:
    DATABASE_URL=postgresql://... python scripts/backtest_calibration.py
    # With tuning flags:
    DATABASE_URL=postgresql://... K_HITS=10 K_TB=10 K_HR=30 python scripts/backtest_calibration.py
    # Grid search:
    DATABASE_URL=postgresql://... python scripts/backtest_calibration.py --grid
"""
import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime
import math
import argparse

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.services.calibrated_probability import CalibratedProbabilityCalculator


def to_float(value) -> float:
    """Convert Decimal/None to float."""
    if value is None:
        return 0.0
    return float(value)


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
    """Compute Brier score (lower is better)."""
    if not predictions:
        return 0.0
    total_error = sum((pred - actual) ** 2 for pred, actual in predictions)
    return total_error / len(predictions)


def compute_log_loss(predictions: List[Tuple[float, int]]) -> float:
    """Compute log loss (lower is better)."""
    if not predictions:
        return 0.0
    epsilon = 1e-15  # Avoid log(0)
    total = 0.0
    for pred, actual in predictions:
        pred = max(epsilon, min(1 - epsilon, pred))
        if actual == 1:
            total -= math.log(pred)
        else:
            total -= math.log(1 - pred)
    return total / len(predictions)


def walk_forward_backtest(db, min_history_games: int = 10, max_test_dates: int = 50):
    """Walk-forward backtest on historical MLB game data using production function."""
    print("=" * 80)
    print("WALK-FORWARD CALIBRATION BACKTEST (Production Function)")
    print("=" * 80)
    print()
    
    # Initialize production calculator
    calc = CalibratedProbabilityCalculator(sport='MLB')
    
    # Get completed MLB game dates
    game_dates = db.query(Game.game_date).filter(
        Game.sport == 'MLB',
        Game.game_status.in_(['final', 'finished'])  # Handle both statuses
    ).distinct().order_by(Game.game_date.desc()).limit(max_test_dates * 2).all()
    
    if not game_dates:
        print("WARNING: No completed MLB games found in database.")
        return None
    
    game_dates = [gd[0] for gd in game_dates]
    # Filter out None dates
    game_dates = [d for d in game_dates if d is not None]
    print(f"Found {len(game_dates)} test dates from {min(game_dates)} to {max(game_dates)}")
    print()
    
    # Stats to test
    stats_to_test = ['hits', 'total_bases', 'home_runs']
    
    # Initialize result trackers per stat AND per line
    results = {}
    for stat in stats_to_test:
        results[stat] = {}
        test_lines = [0.5, 1.5] if stat != 'home_runs' else [0.5]
        for line in test_lines:
            results[stat][line] = {
                'buckets': defaultdict(lambda: {'total': 0, 'hits': 0, 'sum_prob': 0.0}),
                'predictions': [],
                'league_base_rate': None  # Will compute from data
            }
    
    print("Computing league rates from data before each test date (walk-forward)...")
    # We'll compute league mean per stat for each test date using only data before that date
    # For simplicity in this backtest, compute once from all historical data
    # TODO: Make this truly time-varying per test date for perfect walk-forward
    league_rates = {}
    for stat in stats_to_test:
        stat_col = getattr(PlayerGameStat, stat)
        values = db.query(stat_col).filter(
            PlayerGameStat.sport == 'MLB',
            stat_col.isnot(None),
            stat_col >= 0  # Include zeros per fix
        ).all()
        values = [to_float(v[0]) for v in values if v[0] is not None]
        if values:
            league_rates[stat] = sum(values) / len(values)
            
            # Compute empirical base rates per line from all data before first test
            for line in ([0.5, 1.5] if stat != 'home_runs' else [0.5]):
                hits_count = sum(1 for v in values if v > line)
                base_rate = hits_count / len(values) if values else 0.5
                results[stat][line]['league_base_rate'] = base_rate
                print(f"  {stat} OVER {line}: mean={league_rates[stat]:.3f}, base_rate={base_rate:.1%}")
        else:
            league_rates[stat] = 0.5
            for line in ([0.5, 1.5] if stat != 'home_runs' else [0.5]):
                results[stat][line]['league_base_rate'] = 0.5
    
    print()
    print(f"Running walk-forward test on up to {max_test_dates} dates...")
    print()
    
    total_predictions = 0
    dates_processed = 0
    
    for test_date in game_dates:
        if dates_processed >= max_test_dates:
            break
        
        # Get games on test date
        test_games = db.query(Game).filter(
            Game.sport == 'MLB',
            Game.game_date == test_date,
            Game.game_status.in_(['final', 'finished'])
        ).all()
        
        if not test_games:
            continue
        
        dates_processed += 1
        
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
                Game.game_status.in_(['final', 'finished'])
            ).order_by(Game.game_date.desc()).limit(50).all()
            
            if len(history) < min_history_games:
                continue
            
            # For each stat, compute probability and compare
            for stat in stats_to_test:
                actual_value = getattr(stat_row, stat)
                if actual_value is None:
                    continue
                actual_value = to_float(actual_value)
                
                # Get historical values
                stat_values = [to_float(getattr(h, stat)) for h in history 
                              if getattr(h, stat) is not None]
                if len(stat_values) < min_history_games:
                    continue
                
                # Compute mean and std from historical data
                player_mean = sum(stat_values) / len(stat_values)
                if len(stat_values) > 1:
                    player_var = sum((v - player_mean) ** 2 for v in stat_values) / (len(stat_values) - 1)
                    player_std = player_var ** 0.5
                else:
                    player_std = player_mean ** 0.5  # Assume Poisson-like variance
                
                # Test lines
                test_lines = [0.5, 1.5] if stat != 'home_runs' else [0.5]
                for line in test_lines:
                    # Call PRODUCTION function (calculate_probability_for_line)
                    # Cast Decimal to float, use league_mean computed from data before test date
                    prob_result = calc.calculate_probability_for_line(
                        line=float(line),
                        player_mean=player_mean,
                        player_std=player_std,
                        sample_size=len(stat_values),
                        stat_type=stat,
                        league_mean=league_rates[stat],
                        league_std=None  # Production doesn't require league_std for MLB count stats
                    )
                    predicted_prob = prob_result['probability']
                    
                    actual_hit = 1 if actual_value > line else 0
                    
                    # Record result
                    bucket = bucket_probability(predicted_prob)
                    results[stat][line]['buckets'][bucket]['total'] += 1
                    results[stat][line]['buckets'][bucket]['hits'] += actual_hit
                    results[stat][line]['buckets'][bucket]['sum_prob'] += predicted_prob
                    results[stat][line]['predictions'].append((predicted_prob, actual_hit))
                    
                    total_predictions += 1
    
    print(f"COMPLETED: {total_predictions} predictions across {dates_processed} test dates")
    print()
    
    return results


def print_reliability_table(results: Dict):
    """Print reliability table per stat and line (ASCII output)."""
    
    all_buckets = [
        "0.00-0.49", "0.50-0.54", "0.55-0.59", "0.60-0.64", "0.65-0.69",
        "0.70-0.74", "0.75-0.79", "0.80-0.84", "0.85-0.89", "0.90-1.00"
    ]
    
    for stat in results.keys():
        for line in results[stat].keys():
            data = results[stat][line]
            buckets = data['buckets']
            predictions = data['predictions']
            league_base_rate = data['league_base_rate']
            
            print("=" * 80)
            print(f"STAT: {stat.upper()} OVER {line}")
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
                
                bucket_data = buckets[bucket]
                count = bucket_data['total']
                hits = bucket_data['hits']
                avg_pred_prob = bucket_data['sum_prob'] / count
                actual_rate = hits / count
                
                total_preds += count
                total_hits += hits
                total_pred_prob += bucket_data['sum_prob']
                
                error = actual_rate - avg_pred_prob
                error_str = f"{error:+.1%}"
                
                print(f"{bucket:18} | {count:5} | {avg_pred_prob:8.1%} | {actual_rate:6.1%} | {error_str}")
            
            print("-" * 80)
            if total_preds > 0:
                overall_pred = total_pred_prob / total_preds
                overall_actual = total_hits / total_preds
                overall_error = overall_actual - overall_pred
                
                print(f"{'OVERALL':18} | {total_preds:5} | {overall_pred:8.1%} | {overall_actual:6.1%} | {overall_error:+.1%}")
                
                # Metrics
                if predictions:
                    brier = compute_brier_score(predictions)
                    log_loss = compute_log_loss(predictions)
                    
                    # Baseline: always predict league base rate
                    baseline_predictions = [(league_base_rate, actual) for _, actual in predictions]
                    baseline_brier = compute_brier_score(baseline_predictions)
                    baseline_log_loss = compute_log_loss(baseline_predictions)
                    
                    brier_improvement = ((baseline_brier - brier) / baseline_brier) * 100 if baseline_brier > 0 else 0
                    log_loss_improvement = ((baseline_log_loss - log_loss) / baseline_log_loss) * 100 if baseline_log_loss > 0 else 0
                    
                    print()
                    print(f"Brier Score:     {brier:.4f}  (baseline: {baseline_brier:.4f}, improvement: {brier_improvement:+.1f}%)")
                    print(f"Log Loss:        {log_loss:.4f}  (baseline: {baseline_log_loss:.4f}, improvement: {log_loss_improvement:+.1f}%)")
                    print(f"League Base Rate: {league_base_rate:.1%}")
            
            print()
            print()


def main():
    """Run walk-forward calibration backtest."""
    parser = argparse.ArgumentParser(description='MLB calibration backtest')
    parser.add_argument('--k-hits', type=float, help='Prior strength for hits (overrides K_HITS env var)')
    parser.add_argument('--k-tb', type=float, help='Prior strength for total_bases (overrides K_TB env var)')
    parser.add_argument('--k-hr', type=float, help='Prior strength for home_runs (overrides K_HR env var)')
    parser.add_argument('--grid', action='store_true', help='Run grid search over k values')
    args = parser.parse_args()
    
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print()
        print("Usage:")
        print("  DATABASE_URL=postgresql://user:pass@host/db python scripts/backtest_calibration.py")
        print()
        print("Options:")
        print("  --k-hits K    Prior strength for hits (default: 10.0)")
        print("  --k-tb K      Prior strength for total_bases (default: 10.0)")
        print("  --k-hr K      Prior strength for home_runs (default: 30.0)")
        print("  --grid        Run grid search and print tuning table")
        print()
        print("Environment variables (alternative to CLI flags):")
        print("  K_HITS, K_TB, K_HR")
        sys.exit(1)
    
    if args.grid:
        # Grid search mode
        print("=" * 80)
        print("GRID SEARCH MODE")
        print("=" * 80)
        print()
        
        # Define grid
        k_hits_values = [5.0, 10.0, 15.0, 20.0]
        k_tb_values = [5.0, 10.0, 15.0, 20.0]
        k_hr_values = [20.0, 30.0, 40.0, 50.0]
        
        print("Grid:")
        print(f"  K_HITS: {k_hits_values}")
        print(f"  K_TB: {k_tb_values}")
        print(f"  K_HR: {k_hr_values}")
        print()
        
        grid_results = []
        
        for k_hits in k_hits_values:
            for k_tb in k_tb_values:
                for k_hr in k_hr_values:
                    # Set environment variables for this run
                    os.environ['K_HITS'] = str(k_hits)
                    os.environ['K_TB'] = str(k_tb)
                    os.environ['K_HR'] = str(k_hr)
                    
                    # Reload the module to pick up new constants
                    import importlib
                    import app.services.calibrated_probability
                    importlib.reload(app.services.calibrated_probability)
                    
                    print(f"\n{'=' * 80}")
                    print(f"Testing: K_HITS={k_hits}, K_TB={k_tb}, K_HR={k_hr}")
                    print('=' * 80)
                    
                    engine = create_engine(db_url)
                    Session = sessionmaker(bind=engine)
                    db = Session()
                    
                    try:
                        results = walk_forward_backtest(db, min_history_games=10, max_test_dates=50)
                        
                        if results is None:
                            continue
                        
                        # Compute overall metrics
                        overall_metrics = {}
                        for stat in results.keys():
                            for line in results[stat].keys():
                                predictions = results[stat][line]['predictions']
                                if predictions:
                                    brier = compute_brier_score(predictions)
                                    log_loss = compute_log_loss(predictions)
                                    
                                    # Mean predicted vs actual
                                    mean_pred = sum(p for p, _ in predictions) / len(predictions)
                                    mean_actual = sum(a for _, a in predictions) / len(predictions)
                                    
                                    overall_metrics[f"{stat}_{line}"] = {
                                        'brier': brier,
                                        'log_loss': log_loss,
                                        'mean_pred': mean_pred,
                                        'mean_actual': mean_actual,
                                        'error': mean_actual - mean_pred
                                    }
                        
                        grid_results.append({
                            'k_hits': k_hits,
                            'k_tb': k_tb,
                            'k_hr': k_hr,
                            'metrics': overall_metrics
                        })
                        
                    finally:
                        db.close()
        
        # Print grid summary
        print("\n" + "=" * 80)
        print("GRID SEARCH SUMMARY")
        print("=" * 80)
        print()
        print("Stat/Line | K_HITS | K_TB | K_HR | Mean Pred | Mean Actual | Error | Brier | Log Loss")
        print("-" * 120)
        
        for result in grid_results:
            k_hits = result['k_hits']
            k_tb = result['k_tb']
            k_hr = result['k_hr']
            
            for key, metrics in result['metrics'].items():
                print(f"{key:12} | {k_hits:6.1f} | {k_tb:4.1f} | {k_hr:4.1f} | "
                      f"{metrics['mean_pred']:9.1%} | {metrics['mean_actual']:11.1%} | "
                      f"{metrics['error']:+6.1%} | {metrics['brier']:.4f} | {metrics['log_loss']:.4f}")
        
        print()
        return
    
    # Single run mode (with optional CLI overrides)
    if args.k_hits:
        os.environ['K_HITS'] = str(args.k_hits)
    if args.k_tb:
        os.environ['K_TB'] = str(args.k_tb)
    if args.k_hr:
        os.environ['K_HR'] = str(args.k_hr)
    
    # Reload module if any overrides
    if args.k_hits or args.k_tb or args.k_hr:
        import importlib
        import app.services.calibrated_probability
        importlib.reload(app.services.calibrated_probability)
    
    print(f"Using: K_HITS={os.environ.get('K_HITS', '10.0')}, "
          f"K_TB={os.environ.get('K_TB', '10.0')}, "
          f"K_HR={os.environ.get('K_HR', '30.0')}")
    print()
    
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        results = walk_forward_backtest(db, min_history_games=10, max_test_dates=50)
        
        if results is None:
            sys.exit(1)
        
        print_reliability_table(results)
        
        print("=" * 80)
        print("INTERPRETATION")
        print("=" * 80)
        print()
        print("Calibration Error:")
        print("  * Well-calibrated: Actual rate ~= Predicted probability (error near 0%)")
        print("  * Under-confident: Actual rate > Predicted (positive error)")
        print("  * Over-confident: Actual rate < Predicted (negative error)")
        print()
        print("Metrics:")
        print("  * Brier Score: Lower is better (0 = perfect, 0.25 = random)")
        print("  * Log Loss: Lower is better (0 = perfect, infinity = worst)")
        print("  * Compare to baseline (always predict league rate for that line)")
        print()
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
