"""
ML Optimizer Service

Uses machine learning to optimize factor weights based on historical prediction accuracy.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Dict, List, Optional
from datetime import date, timedelta
import numpy as np

# Optional ML imports - backend can run without them until models are trained
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    LinearRegression = None
    RandomForestRegressor = None
    train_test_split = None
    mean_absolute_error = None
    r2_score = None
from app.models.prediction import Prediction
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game


class MLOptimizer:
    """Optimize prediction factor weights using machine learning."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def collect_training_data(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        min_predictions: int = 100
    ) -> Dict:
        """
        Collect historical predictions and actual results for training.
        
        Returns:
            Dict with training data and statistics
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=90)  # Last 90 days
        if end_date is None:
            end_date = date.today() - timedelta(days=1)  # Yesterday
        
        # Get all predictions with actual results
        predictions = self.db.query(Prediction).join(
            Game, Prediction.game_id == Game.game_id
        ).filter(
            and_(
                Game.game_date >= start_date,
                Game.game_date <= end_date,
                Game.game_status == 'finished',
                Prediction.actual_result.isnot(None),
                Prediction.bet_type.in_(['safe', 'standard', 'long_shot'])
            )
        ).all()
        
        if len(predictions) < min_predictions:
            return {
                'error': f'Insufficient data: {len(predictions)} predictions (need {min_predictions})',
                'count': len(predictions)
            }
        
        training_data = []
        
        for pred in predictions:
            # Get actual result
            actual_stat = self.db.query(PlayerGameStat).filter(
                and_(
                    PlayerGameStat.player_id == pred.player_id,
                    PlayerGameStat.game_id == pred.game_id
                )
            ).first()
            
            if not actual_stat:
                continue
            
            # Get actual value based on stat type
            if pred.stat_type == 'points':
                actual_value = actual_stat.points
            elif pred.stat_type == 'rebounds':
                actual_value = actual_stat.rebounds
            elif pred.stat_type == 'assists':
                actual_value = actual_stat.assists
            else:
                continue
            
            # Extract factor values from reasoning (if stored)
            # For now, we'll use prediction features
            training_data.append({
                'prediction_id': pred.prediction_id,
                'predicted_mean': pred.distribution_mean,
                'predicted_std': pred.distribution_std_dev,
                'actual_value': actual_value,
                'error': abs(pred.distribution_mean - actual_value),
                'stat_type': pred.stat_type,
                'confidence_level': pred.confidence_level,
                'sample_size': pred.sample_size
            })
        
        return {
            'count': len(training_data),
            'data': training_data,
            'start_date': start_date,
            'end_date': end_date
        }
    
    def optimize_factor_weights(
        self,
        training_data: List[Dict]
    ) -> Dict:
        """
        Train ML model to optimize factor weights.
        
        Returns:
            Dict with optimized weights and model performance
        """
        if not SKLEARN_AVAILABLE:
            return {
                'error': 'scikit-learn is not installed. Install it with: pip install scikit-learn'
            }
        
        if len(training_data) < 50:
            return {'error': 'Insufficient training data'}
        
        # Prepare features and target
        X = []
        y = []
        
        for sample in training_data:
            # Features: prediction characteristics
            features = [
                sample['predicted_mean'],
                sample['predicted_std'],
                sample['sample_size'],
                1 if sample['confidence_level'] == 'HIGH' else 0,
                1 if sample['confidence_level'] == 'MEDIUM' else 0,
            ]
            X.append(features)
            y.append(sample['actual_value'])
        
        X = np.array(X)
        y = np.array(y)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train models
        models = {
            'linear': LinearRegression(),
            'random_forest': RandomForestRegressor(n_estimators=100, random_state=42, max_depth=10)
        }
        
        results = {}
        
        for model_name, model in models.items():
            # Train
            model.fit(X_train, y_train)
            
            # Predict
            y_pred_train = model.predict(X_train)
            y_pred_test = model.predict(X_test)
            
            # Evaluate
            train_mae = mean_absolute_error(y_train, y_pred_train)
            test_mae = mean_absolute_error(y_test, y_pred_test)
            train_r2 = r2_score(y_train, y_pred_train)
            test_r2 = r2_score(y_test, y_pred_test)
            
            results[model_name] = {
                'train_mae': round(train_mae, 3),
                'test_mae': round(test_mae, 3),
                'train_r2': round(train_r2, 3),
                'test_r2': round(test_r2, 3),
                'model': model
            }
        
        # Select best model
        best_model_name = min(results.keys(), key=lambda k: results[k]['test_mae'])
        best_model = results[best_model_name]['model']
        
        # Extract feature importance (for Random Forest)
        feature_importance = None
        if hasattr(best_model, 'feature_importances_'):
            feature_importance = {
                'predicted_mean': float(best_model.feature_importances_[0]),
                'predicted_std': float(best_model.feature_importances_[1]),
                'sample_size': float(best_model.feature_importances_[2]),
                'high_confidence': float(best_model.feature_importances_[3]),
                'medium_confidence': float(best_model.feature_importances_[4])
            }
        
        return {
            'best_model': best_model_name,
            'performance': results[best_model_name],
            'all_results': results,
            'feature_importance': feature_importance,
            'model': best_model
        }
    
    def calibrate_probabilities(
        self,
        training_data: List[Dict]
    ) -> Dict:
        """
        Calibrate probability predictions to match actual hit rates.
        
        This compares predicted probabilities to actual hit rates and calculates
        adjustment factors to make predictions more accurate.
        
        Returns:
            Dict with calibration adjustments by probability range
        """
        from app.models.prediction import Prediction
        from app.models.player_game_stat import PlayerGameStat
        
        # Group predictions by probability ranges
        prob_ranges = {
            '0.70-0.75': [],
            '0.75-0.80': [],
            '0.80-0.85': [],
            '0.85-0.90': [],
            '0.90-0.95': [],
            '0.95-1.00': []
        }
        
        # Get predictions with actual results
        for sample in training_data:
            pred_id = sample.get('prediction_id')
            if not pred_id:
                continue
            
            # Get the prediction to find its probability
            pred = self.db.query(Prediction).filter(Prediction.prediction_id == pred_id).first()
            if not pred:
                continue
            
            # Determine which probability to use based on bet type
            predicted_prob = None
            if pred.bet_type == 'safe':
                predicted_prob = pred.safe_probability
            elif pred.bet_type == 'standard':
                predicted_prob = pred.standard_probability
            elif pred.bet_type == 'long_shot':
                predicted_prob = pred.long_shot_probability
            
            if predicted_prob is None:
                continue
            
            # Get actual result
            actual_value = sample.get('actual_value')
            predicted_mean = sample.get('predicted_mean')
            
            if actual_value is None or predicted_mean is None:
                continue
            
            # Determine if bet hit (actual >= predicted mean for "over" bets)
            # For now, we'll use a simple threshold: actual >= predicted mean
            hit = actual_value >= predicted_mean
            
            # Find the appropriate probability range
            for range_name in prob_ranges.keys():
                range_parts = range_name.split('-')
                if len(range_parts) == 2:
                    try:
                        min_prob = float(range_parts[0])
                        max_prob = float(range_parts[1])
                        if min_prob <= predicted_prob < max_prob:
                            prob_ranges[range_name].append({
                                'predicted_prob': predicted_prob,
                                'hit': hit,
                                'actual_value': actual_value,
                                'predicted_mean': predicted_mean
                            })
                            break
                    except ValueError:
                        continue
        
        # Calculate actual hit rates for each range
        calibration = {}
        for range_name, samples in prob_ranges.items():
            if len(samples) >= 10:  # Need at least 10 samples for reliable calibration
                actual_hit_rate = sum(1 for s in samples if s['hit']) / len(samples)
                range_parts = range_name.split('-')
                expected_prob = float(range_parts[0]) if len(range_parts) == 2 else 0.75
                
                # Calculate adjustment factor
                # If actual < expected, we're overconfident, so reduce probability
                # If actual > expected, we're underconfident, so increase probability
                adjustment = actual_hit_rate / expected_prob if expected_prob > 0 else 1.0
                
                calibration[range_name] = {
                    'expected': expected_prob,
                    'actual': round(actual_hit_rate, 3),
                    'adjustment': round(adjustment, 3),
                    'sample_count': len(samples)
                }
        
        return calibration

