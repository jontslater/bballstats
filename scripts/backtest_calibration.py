#!/usr/bin/env python3
"""
Walk-forward backtest of calibrated probabilities using discrete models.

For count stats (hits, home_runs, total_bases), uses Poisson/Negative Binomial
distribution with shrinkage toward league rate.

Usage:
    DATABASE_URL=postgresql://... python scripts/backtest_calibration.py
"""
import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
from datetime import datetime
import math

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from scipy import stats as scipy_stats


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


def calculate_discrete_probability(
    values: List[int],
    line: float,
    league_rate: float,
    stat_name: str
) -> float:
    """
    Calculate P(X > line) using discrete Poisson/Negative Binomial model.
    
    For count stats, use proper discrete distribution instead of Normal/Student-t.
    Shrinks player rate toward league rate.
    
    Args:
        values: List of historical stat values
        line: Betting line (e.g., 0.5 for OVER 0.5)
        league_rate: League average per-game rate for this stat
        stat_name: Name of stat (for shrinkage tuning)
    
    Returns:
        P(X > line) using Poisson or Negative Binomial
    """
    if not values:
        return 0.5
    
    sample_size = len(values)
    player_mean = sum(values) / sample_size
    
    # Shrinkage toward league rate (stronger for rare events like home_runs)
    if stat_name == 'home_runs':
        prior_strength = 20.0  # Strong shrinkage for HRs
    else:
        prior_strength = 10.0  # Moderate shrinkage for hits/TB
    
    weight_player = sample_size / (sample_size + prior_strength)
    shrunk_rate = weight_player * player_mean + (1 - weight_player) * league_rate
    
    # Estimate dispersion (variance / mean ratio)
    if sample_size > 1:
        player_var = sum((v - player_mean) ** 2 for v in values) / (sample_size - 1)
        dispersion = player_var / player_mean if player_mean > 0 else 1.0
    else:
        dispersion = 1.0
    
    # Choose distribution based on dispersion
    if dispersion > 1.5:
        # Over-dispersed: use Negative Binomial
        # NB parameterization: r = mean^2 / (var - mean), p = mean / var
        if player_var > player_mean and player_mean > 0:
            r = (player_mean ** 2) / (player_var - player_mean)
            p_nb = player_mean / player_var
            # P(X > line) = 1 - P(X <= line) = 1 - CDF(floor(line))
            prob = 1.0 - scipy_stats.nbinom.cdf(int(line), r, p_nb)
        else:
            # Fall back to Poisson
            prob = 1.0 - scipy_stats.poisson.cdf(int(line), shrunk_rate)
    else:
        # Use Poisson (simpler, works well for count data)
        prob = 1.0 - scipy_stats.poisson.cdf(int(line), shrunk_rate)
    
    return max(0.01, min(0.99, prob))


def walk_forward_backtest(db, min_history_games: int = 10, max_test_dates: int = 50):
    """Walk-forward backtest on historical MLB game data."""
    print("=" * 80)
    print("WALK-FORWARD CALIBRATION BACKTEST (Discrete Models)")
    print("=" * 80)
    print()
    
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
    
    print("Computing league rates (from all data for now - TODO: time-varying)...")
    league_rates = {}
    for stat in stats_to_test:
        stat_col = getattr(PlayerGameStat, stat)
        values = db.query(stat_col).filter(
            PlayerGameStat.sport == 'MLB',
            stat_col.isnot(None),
            stat_col >= 0
        ).all()
        values = [to_float(v[0]) for v in values if v[0] is not None]
        if values:
            league_rates[stat] = sum(values) / len(values)
            
            # Compute empirical base rates per line
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
                
                # Test lines
                test_lines = [0.5, 1.5] if stat != 'home_runs' else [0.5]
                for line in test_lines:
                    # Compute probability using discrete model
                    predicted_prob = calculate_discrete_probability(
                        stat_values, line, league_rates[stat], stat
                    )
                    
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
    """Print reliability table per stat and line."""
    
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
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print()
        print("Usage:")
        print("  DATABASE_URL=postgresql://user:pass@host/db python scripts/backtest_calibration.py")
        sys.exit(1)
    
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
