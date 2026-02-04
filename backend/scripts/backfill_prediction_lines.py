"""
Backfill Line Values for Existing Predictions

This script calculates and populates line values for predictions that are missing them.
This fixes the "NaN" display issue in the dashboard.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.prediction import Prediction
from typing import Dict, List
import statistics


class LineBackfiller:
    """Backfill missing line values for predictions."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_line_from_distribution(self, prediction: Prediction) -> float:
        """
        Calculate appropriate line based on prediction data.

        For predictions with distribution data, use percentiles as line estimates:
        - Safe bets: 75th percentile (higher threshold)
        - Standard bets: 50th percentile (median)
        - Long shots: 25th percentile (lower threshold)
        """
        if not prediction.distribution_mean:
            return 0.0

        base_value = prediction.distribution_mean

        # Adjust based on bet type
        if prediction.bet_type == 'safe':
            # Safe bets target higher values (75th percentile equivalent)
            line = base_value * 1.2  # Rough estimate for 75th percentile
        elif prediction.bet_type == 'standard':
            # Standard bets target median values
            line = base_value
        elif prediction.bet_type == 'long_shot':
            # Long shots target lower values (25th percentile equivalent)
            line = base_value * 0.8  # Rough estimate for 25th percentile
        else:
            line = base_value

        # Round to appropriate decimal places based on stat type
        if prediction.stat_type in ['points', 'rebounds', 'assists']:
            return round(line, 1)  # 1 decimal place for counting stats
        else:
            return round(line, 2)  # 2 decimal places for rate stats

    def calculate_probability_defaults(self, prediction: Prediction) -> float:
        """Calculate default probability based on bet type if missing."""
        if prediction.bet_type == 'safe':
            return 0.75
        elif prediction.bet_type == 'standard':
            return 0.60  # Around 60% for standard bets
        elif prediction.bet_type == 'long_shot':
            return 0.25  # Around 25% for long shots
        else:
            return 0.50  # Default fallback

    def backfill_predictions(self, limit: int = 1000) -> Dict[str, int]:
        """
        Backfill missing line and probability values for predictions.

        Args:
            limit: Maximum number of predictions to process

        Returns:
            Dict with counts of processed predictions
        """
        print("🔍 Finding predictions with missing line values...")

        # Find predictions with null line values
        predictions_to_update = self.db.query(Prediction).filter(
            Prediction.safe_line.is_(None) |
            Prediction.standard_line.is_(None) |
            Prediction.long_shot_line.is_(None)
        ).limit(limit).all()

        print(f"📊 Found {len(predictions_to_update)} predictions to update")

        updated_count = 0
        skipped_count = 0

        for prediction in predictions_to_update:
            try:
                # Calculate appropriate line based on bet type
                if prediction.bet_type == 'safe' and prediction.safe_line is None:
                    prediction.safe_line = self.calculate_line_from_distribution(prediction)
                    print(f"✅ Updated safe_line for {prediction.player_name} {prediction.stat_type}: {prediction.safe_line}")

                elif prediction.bet_type == 'standard' and prediction.standard_line is None:
                    prediction.standard_line = self.calculate_line_from_distribution(prediction)
                    print(f"✅ Updated standard_line for {prediction.player_name} {prediction.stat_type}: {prediction.standard_line}")

                elif prediction.bet_type == 'long_shot' and prediction.long_shot_line is None:
                    prediction.long_shot_line = self.calculate_line_from_distribution(prediction)
                    print(f"✅ Updated long_shot_line for {prediction.player_name} {prediction.stat_type}: {prediction.long_shot_line}")

                # Also backfill probabilities if missing
                if prediction.bet_type == 'safe' and prediction.safe_probability is None:
                    prediction.safe_probability = self.calculate_probability_defaults(prediction)
                elif prediction.bet_type == 'standard' and prediction.standard_probability is None:
                    prediction.standard_probability = self.calculate_probability_defaults(prediction)
                elif prediction.bet_type == 'long_shot' and prediction.long_shot_probability is None:
                    prediction.long_shot_probability = self.calculate_probability_defaults(prediction)

                updated_count += 1

            except Exception as e:
                print(f"❌ Error updating prediction {prediction.prediction_id}: {e}")
                skipped_count += 1
                continue

        # Commit all changes
        try:
            self.db.commit()
            print(f"💾 Committed {updated_count} updates to database")
        except Exception as e:
            print(f"❌ Error committing changes: {e}")
            self.db.rollback()
            return {'updated': 0, 'skipped': len(predictions_to_update)}

        return {
            'updated': updated_count,
            'skipped': skipped_count,
            'total_processed': len(predictions_to_update)
        }


def main():
    """Main function to run the backfill process."""
    print("🚀 Starting prediction line backfill process...")

    db = SessionLocal()
    try:
        backfiller = LineBackfiller(db)
        results = backfiller.backfill_predictions(limit=5000)  # Process up to 5000 predictions

        print("\n📈 Backfill Results:")
        print(f"  ✅ Updated: {results['updated']} predictions")
        print(f"  ❌ Skipped: {results['skipped']} predictions")
        print(f"  📊 Total processed: {results['total_processed']} predictions")

        if results['updated'] > 0:
            print("\n🎯 Dashboard should now show proper line values instead of 'NaN'!")
        else:
            print("\nℹ️  No predictions needed updating - they may already have line values.")

    except Exception as e:
        print(f"❌ Error during backfill: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()