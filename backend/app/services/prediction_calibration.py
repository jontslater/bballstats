"""
Prediction Calibration Service

Tracks actual vs predicted outcomes and calibrates probabilities to improve accuracy.
This ensures that when we predict 75%, it actually hits ~75% of the time.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import Dict, List, Optional
from datetime import date, timedelta
from app.models.prediction import Prediction
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
import json


class PredictionCalibration:
    """Calibrate prediction probabilities based on actual outcomes."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def update_predictions_with_results(self, game_date: Optional[date] = None) -> Dict:
        """
        Update predictions with actual game results.
        
        Args:
            game_date: Specific date to update, or None for all finished games without results
        
        Returns:
            Dict with update statistics
        """
        # Get finished games with predictions that don't have actual results yet
        query = self.db.query(Prediction).join(
            Game, Prediction.game_id == Game.game_id
        ).filter(
            and_(
                Game.game_status == 'finished',
                Prediction.actual_result.is_(None)
            )
        )
        
        if game_date:
            query = query.filter(Game.game_date == game_date)
        
        predictions = query.all()
        total_count = len(predictions)
        
        print(f"📊 Found {total_count} predictions to update")
        if game_date:
            print(f"   Date: {game_date}")
        else:
            print(f"   Processing all finished games without results")
        
        updated = 0
        skipped = 0
        skipped_no_stat = 0
        skipped_no_value = 0
        skipped_unsupported_type = 0
        errors = 0
        
        # Process in batches for progress updates
        batch_size = 100
        for i, pred in enumerate(predictions, 1):
            try:
                # Progress logging
                if i % batch_size == 0 or i == total_count:
                    print(f"   Processing: {i}/{total_count} ({i*100//total_count}%) - Updated: {updated}, Skipped: {skipped}")
                
                # Get actual stat from game
                stat = self.db.query(PlayerGameStat).filter(
                    and_(
                        PlayerGameStat.player_id == pred.player_id,
                        PlayerGameStat.game_id == pred.game_id
                    )
                ).first()
                
                if not stat:
                    skipped += 1
                    skipped_no_stat += 1
                    continue
                
                # Get actual value based on stat type
                if pred.stat_type == 'points':
                    actual_value = stat.points
                elif pred.stat_type == 'rebounds':
                    actual_value = stat.rebounds
                elif pred.stat_type == 'assists':
                    actual_value = stat.assists
                else:
                    skipped += 1
                    skipped_unsupported_type += 1
                    continue
                
                if actual_value is None:
                    skipped += 1
                    skipped_no_value += 1
                    continue
                
                # Update prediction with actual result
                pred.actual_result = int(actual_value)
                
                # Check if bets hit
                if pred.safe_line:
                    pred.hit_safe = (actual_value >= pred.safe_line)
                if pred.standard_line:
                    pred.hit_standard = (actual_value >= pred.standard_line)
                if pred.long_shot_line:
                    pred.hit_long_shot = (actual_value >= pred.long_shot_line)
                
                updated += 1
                
            except Exception as e:
                errors += 1
                print(f"   Error updating prediction {pred.prediction_id}: {e}")
                continue
        
        if updated > 0:
            print(f"   Committing {updated} updates to database...")
            self.db.commit()
            print(f"   ✅ Commit successful")
        
        print(f"\n📈 Update Summary:")
        print(f"   Total processed: {total_count}")
        print(f"   ✅ Updated: {updated}")
        print(f"   ⏭️  Skipped: {skipped}")
        if skipped > 0:
            print(f"      - No player stat record: {skipped_no_stat}")
            print(f"      - No stat value (NULL): {skipped_no_value}")
            print(f"      - Unsupported stat type: {skipped_unsupported_type}")
        print(f"   ❌ Errors: {errors}")
        
        return {
            'updated': updated,
            'skipped': skipped,
            'skipped_details': {
                'no_stat_record': skipped_no_stat,
                'no_value': skipped_no_value,
                'unsupported_type': skipped_unsupported_type
            },
            'errors': errors,
            'total': total_count
        }
    
    def calculate_calibration_curves(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_samples: int = 20
    ) -> Dict:
        """
        Calculate calibration curves by comparing predicted probabilities to actual hit rates.
        
        For each predicted probability range (e.g., 70-75%, 75-80%), calculate:
        - Number of predictions
        - Actual hit rate
        - Calibration adjustment needed
        
        Returns:
            Dict with calibration data by bet type and probability range
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=90)  # Last 90 days
        if end_date is None:
            end_date = date.today() - timedelta(days=1)
        
        calibration_data = {
            'safe': {},
            'standard': {},
            'long_shot': {}
        }
        
        # Get all predictions with actual results
        predictions = self.db.query(Prediction).join(
            Game, Prediction.game_id == Game.game_id
        ).filter(
            and_(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                Game.game_status == 'finished',
                Prediction.actual_result.isnot(None)
            )
        ).all()
        
        # Calibrate each bet type
        for bet_type in ['safe', 'standard', 'long_shot']:
            # Group predictions by probability ranges
            ranges = [
                (0.70, 0.75, '70-75'),
                (0.75, 0.80, '75-80'),
                (0.80, 0.85, '80-85'),
                (0.85, 0.90, '85-90'),
                (0.90, 0.95, '90-95'),
                (0.95, 1.00, '95-100')
            ]
            
            for min_prob, max_prob, label in ranges:
                # Filter predictions in this probability range
                if bet_type == 'safe':
                    filtered = [p for p in predictions 
                               if p.safe_probability and 
                               min_prob <= p.safe_probability < max_prob and
                               p.hit_safe is not None]
                    prob_values = [p.safe_probability for p in filtered]
                    hit_values = [p.hit_safe for p in filtered]
                elif bet_type == 'standard':
                    filtered = [p for p in predictions 
                               if p.standard_probability and 
                               min_prob <= p.standard_probability < max_prob and
                               p.hit_standard is not None]
                    prob_values = [p.standard_probability for p in filtered]
                    hit_values = [p.hit_standard for p in filtered]
                else:  # long_shot
                    filtered = [p for p in predictions 
                               if p.long_shot_probability and 
                               min_prob <= p.long_shot_probability < max_prob and
                               p.hit_long_shot is not None]
                    prob_values = [p.long_shot_probability for p in filtered]
                    hit_values = [p.hit_long_shot for p in filtered]
                
                if len(filtered) < min_samples:
                    continue
                
                # Calculate actual hit rate
                actual_hit_rate = sum(hit_values) / len(hit_values) if hit_values else 0.0
                predicted_prob = sum(prob_values) / len(prob_values) if prob_values else 0.0
                
                # Calculate calibration adjustment
                # If predicted 75% but only hit 65%, we need to adjust down by 10%
                calibration_adjustment = actual_hit_rate - predicted_prob
                
                calibration_data[bet_type][label] = {
                    'sample_size': len(filtered),
                    'predicted_probability': round(predicted_prob, 3),
                    'actual_hit_rate': round(actual_hit_rate, 3),
                    'calibration_adjustment': round(calibration_adjustment, 3),
                    'min_prob': min_prob,
                    'max_prob': max_prob
                }
        
        return calibration_data
    
    def get_calibrated_probability(
        self,
        raw_probability: float,
        bet_type: str,
        calibration_data: Optional[Dict] = None
    ) -> float:
        """
        Apply calibration adjustment to a raw probability.
        
        Args:
            raw_probability: Raw probability from distribution (0.0 to 1.0)
            bet_type: 'safe', 'standard', or 'long_shot'
            calibration_data: Calibration data dict (if None, loads fresh)
        
        Returns:
            Calibrated probability
        """
        if calibration_data is None:
            calibration_data = self.calculate_calibration_curves()
        
        if bet_type not in calibration_data:
            return raw_probability
        
        # Find the probability range this falls into
        for label, data in calibration_data[bet_type].items():
            if data['min_prob'] <= raw_probability < data['max_prob']:
                # Apply calibration adjustment
                calibrated = raw_probability + data['calibration_adjustment']
                # Clamp to valid range
                return max(0.0, min(1.0, calibrated))
        
        # If no range matches, return original
        return raw_probability
    
    def get_calibration_stats(self) -> Dict:
        """
        Get overall calibration statistics.
        
        Returns:
            Dict with overall accuracy metrics
        """
        # Get all predictions with results from last 90 days
        start_date = date.today() - timedelta(days=90)
        
        predictions = self.db.query(Prediction).join(
            Game, Prediction.game_id == Game.game_id
        ).filter(
            and_(
                Game.game_date >= start_date,
                Game.game_status == 'finished',
                Prediction.actual_result.isnot(None)
            )
        ).all()
        
        stats = {
            'safe': {'total': 0, 'hits': 0, 'avg_prob': 0.0},
            'standard': {'total': 0, 'hits': 0, 'avg_prob': 0.0},
            'long_shot': {'total': 0, 'hits': 0, 'avg_prob': 0.0}
        }
        
        safe_probs = []
        standard_probs = []
        long_shot_probs = []
        
        for pred in predictions:
            if pred.hit_safe is not None and pred.safe_probability:
                stats['safe']['total'] += 1
                if pred.hit_safe:
                    stats['safe']['hits'] += 1
                safe_probs.append(pred.safe_probability)
            
            if pred.hit_standard is not None and pred.standard_probability:
                stats['standard']['total'] += 1
                if pred.hit_standard:
                    stats['standard']['hits'] += 1
                standard_probs.append(pred.standard_probability)
            
            if pred.hit_long_shot is not None and pred.long_shot_probability:
                stats['long_shot']['total'] += 1
                if pred.hit_long_shot:
                    stats['long_shot']['hits'] += 1
                long_shot_probs.append(pred.long_shot_probability)
        
        # Calculate hit rates and average probabilities
        for bet_type in stats:
            if stats[bet_type]['total'] > 0:
                stats[bet_type]['hit_rate'] = stats[bet_type]['hits'] / stats[bet_type]['total']
            else:
                stats[bet_type]['hit_rate'] = 0.0
            
            probs = safe_probs if bet_type == 'safe' else (standard_probs if bet_type == 'standard' else long_shot_probs)
            if probs:
                stats[bet_type]['avg_prob'] = sum(probs) / len(probs)
        
        return stats

