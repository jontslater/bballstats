#!/usr/bin/env python3
"""
Analyze PAR (Points + Assists + Rebounds) vs Individual Stats Efficiency

This script analyzes historical prediction performance to validate whether
PAR predictions are indeed easier to hit than individual stat predictions.
"""

import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Prediction, PlayerGameStat, Game


def analyze_stat_hit_rates(db: Session, days_back: int = 30):
    """
    Analyze hit rates for different stat types over the last N days.

    Returns:
        Dict with hit rate analysis by stat type
    """
    # Calculate date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    print(f"Analyzing predictions from {start_date} to {end_date}")

    # Get all completed predictions in date range
    predictions = db.query(Prediction).join(Game).filter(
        Game.game_date.between(start_date, end_date),
        Game.game_status == 'finished',
        Prediction.sport == 'NBA'
    ).all()

    print(f"Found {len(predictions)} NBA predictions to analyze")

    # Group by stat type
    stat_analysis = defaultdict(lambda: {
        'total_predictions': 0,
        'hits': 0,
        'hit_rate': 0.0,
        'avg_line': 0.0,
        'total_lines': 0
    })

    for pred in predictions:
        stat_type = pred.stat_type
        analysis = stat_analysis[stat_type]

        analysis['total_predictions'] += 1

        # Check if prediction hit
        # For simplicity, we'll assume the prediction result is stored
        # In a real implementation, you'd need to check actual vs predicted
        # For now, let's just count total predictions per stat type

        # Get the actual game stats
        actual_stats = db.query(PlayerGameStat).filter(
            PlayerGameStat.game_id == pred.game_id,
            PlayerGameStat.player_id == pred.player_id
        ).first()

        if actual_stats:
            # Calculate actual value based on stat type
            if stat_type == 'points':
                actual_value = actual_stats.points or 0
            elif stat_type == 'rebounds':
                actual_value = actual_stats.rebounds or 0
            elif stat_type == 'assists':
                actual_value = actual_stats.assists or 0
            elif stat_type == 'pts+ast+reb':
                actual_value = (actual_stats.points or 0) + (actual_stats.assists or 0) + (actual_stats.rebounds or 0)
            else:
                continue  # Skip unsupported stat types

            # Get prediction details
            if pred.bet_type == 'safe':
                pred_line = pred.safe_line
                pred_over_under = 'over' if pred_line > 0 else 'under'
            elif pred.bet_type == 'standard':
                pred_line = pred.standard_line
                pred_over_under = 'over' if pred_line > 0 else 'under'
            else:
                continue  # Skip other bet types

            # Determine if prediction hit
            line_value = abs(pred_line)
            if pred_over_under == 'over' and actual_value > line_value:
                analysis['hits'] += 1
            elif pred_over_under == 'under' and actual_value < line_value:
                analysis['hits'] += 1

            analysis['total_lines'] += line_value
            analysis['avg_line'] += line_value

    # Calculate final stats
    for stat_type, analysis in stat_analysis.items():
        if analysis['total_predictions'] > 0:
            analysis['hit_rate'] = analysis['hits'] / analysis['total_predictions']
            analysis['avg_line'] = analysis['total_lines'] / analysis['total_predictions']

    return dict(stat_analysis)


def print_analysis_results(analysis_results):
    """Print formatted analysis results."""
    print("\n" + "="*60)
    print("NBA STAT PREDICTION HIT RATE ANALYSIS")
    print("="*60)

    # Sort by hit rate (highest first)
    sorted_stats = sorted(analysis_results.items(), key=lambda x: x[1]['hit_rate'], reverse=True)

    print(f"{'Stat Type':<25} {'Predictions':<12} {'Hits':<8} {'Hit Rate':<10} {'Avg Line':<10}")
    print("-" * 65)

    for stat_type, stats in sorted_stats:
        if stats['total_predictions'] > 0:
            hit_rate_pct = f"{stats['hit_rate']*100:.1f}%"
            avg_line = f"{stats['avg_line']:.1f}"
            print(f"{stat_type:<25} {stats['total_predictions']:<12} {stats['hits']:<8} {hit_rate_pct:<10} {avg_line:<10}")

    print("\n" + "="*60)

    # Check if PAR is indeed easier
    if 'pts+ast+reb' in analysis_results and len(analysis_results) > 1:
        par_stats = analysis_results['pts+ast+reb']
        other_stats = {k: v for k, v in analysis_results.items() if k != 'pts+ast+reb' and v['total_predictions'] > 0}

        if other_stats:
            avg_other_hit_rate = sum(s['hit_rate'] for s in other_stats.values()) / len(other_stats)
            par_hit_rate = par_stats['hit_rate']

            print("COMPARISON: PAR vs Individual Stats")
            print(f"PAR Hit Rate: {par_hit_rate*100:.1f}%")
            print(f"Average Individual Stat Hit Rate: {avg_other_hit_rate*100:.1f}%")
            print(f"Difference: {(par_hit_rate - avg_other_hit_rate)*100:+.1f} percentage points")

            if par_hit_rate > avg_other_hit_rate:
                print("✅ CONFIRMED: PAR predictions are easier to hit than individual stats!")
            else:
                print("❌ NOT CONFIRMED: PAR predictions are NOT easier than individual stats.")
        else:
            print("⚠️  Not enough data for comparison (only PAR stats found)")


def main():
    """Main analysis function."""
    print("NBA PAR vs Individual Stats Efficiency Analysis")
    print("This will analyze prediction hit rates over the last 30 days")

    db = SessionLocal()
    try:
        analysis_results = analyze_stat_hit_rates(db, days_back=30)
        print_analysis_results(analysis_results)
    finally:
        db.close()


if __name__ == "__main__":
    main()