"""
Machine Learning Ensemble Service

Advanced ML models for player performance prediction using ensemble methods.
Combines multiple algorithms for superior accuracy and confidence scoring.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sqlalchemy import and_, func, desc
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Tuple, Any
from app.models.player_game_stat import PlayerGameStat
from app.models.game import Game
from app.models.player import Player
import pickle
import os
from datetime import datetime, timedelta
import statistics


class MLEnsembleService:
    """Machine Learning ensemble for player performance prediction."""

    def __init__(self, db: Session):
        self.db = db
        self.models_dir = "backend/ml_models"
        self.ensure_models_dir()

        # Initialize models
        self.models = {
            'rf': RandomForestRegressor(n_estimators=100, random_state=42),
            'gb': GradientBoostingRegressor(n_estimators=100, random_state=42),
            'ridge': Ridge(alpha=0.1)
        }

        self.scaler = StandardScaler()
        self.feature_importance = {}
        self.model_performance = {}

    def ensure_models_dir(self):
        """Ensure models directory exists."""
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)

    def build_training_dataset(
        self,
        player_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        min_games: int = 50
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Build comprehensive training dataset for a player and stat type.

        Args:
            player_id: Player to build model for
            stat_type: Stat type to predict
            season_id: Season for training
            min_games: Minimum games required for training

        Returns:
            Tuple of (features DataFrame, target Series)
        """
        if season_id is None:
            season = self.db.query(Season).filter(Season.is_current == True).first()
            if not season:
                raise ValueError("No current season found")
            season_id = season.season_id

        # Get all games for player
        games_data = self.db.query(PlayerGameStat, Game).join(
            Game, PlayerGameStat.game_id == Game.game_id
        ).filter(
            and_(
                PlayerGameStat.player_id == player_id,
                Game.season_id == season_id,
                Game.game_status == 'finished',
                PlayerGameStat.minutes_played > 5  # At least 5 minutes
            )
        ).order_by(Game.game_date).all()

        if len(games_data) < min_games:
            raise ValueError(f"Insufficient data: {len(games_data)} games, need {min_games}")

        training_data = []

        for i, (player_stat, game) in enumerate(games_data):
            if i < 5:  # Need at least 5 prior games for features
                continue

            # Extract target (actual performance)
            target_value = self._extract_stat_value(player_stat, stat_type)

            # Build feature vector
            features = self._build_feature_vector(
                player_id, games_data[:i], game, stat_type, season_id
            )

            if features:
                training_data.append({
                    'features': features,
                    'target': target_value,
                    'game_id': game.game_id
                })

        if not training_data:
            raise ValueError("No valid training data generated")

        # Convert to DataFrame
        feature_df = pd.DataFrame([d['features'] for d in training_data])
        target_series = pd.Series([d['target'] for d in training_data])

        return feature_df, target_series

    def _build_feature_vector(
        self,
        player_id: int,
        prior_games: List[Tuple[PlayerGameStat, Game]],
        current_game: Game,
        stat_type: str,
        season_id: int
    ) -> Optional[Dict[str, float]]:
        """
        Build comprehensive feature vector for prediction.
        """
        if len(prior_games) < 5:
            return None

        features = {}

        # Basic recent performance features
        recent_stats = [stat for stat, game in prior_games[-10:]]  # Last 10 games
        features.update(self._extract_recent_performance_features(recent_stats, stat_type))

        # Trend features
        features.update(self._extract_trend_features(prior_games, stat_type))

        # Opponent/context features
        features.update(self._extract_opponent_features(current_game, stat_type))

        # Physical/health features
        features.update(self._extract_health_features(prior_games, current_game))

        # Advanced analytics features
        features.update(self._extract_advanced_analytics_features(prior_games, stat_type))

        # Situational features
        features.update(self._extract_situational_features(current_game))

        return features

    def _extract_recent_performance_features(
        self,
        recent_stats: List[PlayerGameStat],
        stat_type: str
    ) -> Dict[str, float]:
        """Extract recent performance features."""
        features = {}

        # Recent averages (last 3, 5, 10 games)
        for period in [3, 5, 10]:
            if len(recent_stats) >= period:
                values = [self._extract_stat_value(stat, stat_type) for stat in recent_stats[-period:]]
                features[f'avg_last_{period}'] = sum(values) / len(values)
                features[f'std_last_{period}'] = statistics.stdev(values) if len(values) > 1 else 0

        # Recent form indicators
        if len(recent_stats) >= 5:
            last_5_avg = sum(self._extract_stat_value(stat, stat_type) for stat in recent_stats[-5:]) / 5
            season_avg = sum(self._extract_stat_value(stat, stat_type) for stat in recent_stats) / len(recent_stats)
            features['recent_vs_season'] = last_5_avg / season_avg if season_avg > 0 else 1.0

        return features

    def _extract_trend_features(
        self,
        prior_games: List[Tuple[PlayerGameStat, Game]],
        stat_type: str
    ) -> Dict[str, float]:
        """Extract performance trend features."""
        features = {}

        if len(prior_games) < 10:
            return features

        # Calculate trends over different periods
        values = [self._extract_stat_value(stat, stat_type) for stat, game in prior_games]

        for period in [10, 20]:
            if len(values) >= period:
                recent = values[-period//2:]
                earlier = values[-period:-period//2]

                if recent and earlier:
                    recent_avg = sum(recent) / len(recent)
                    earlier_avg = sum(earlier) / len(earlier)
                    features[f'trend_{period}'] = (recent_avg - earlier_avg) / earlier_avg if earlier_avg > 0 else 0

        return features

    def _extract_opponent_features(self, game: Game, stat_type: str) -> Dict[str, float]:
        """Extract opponent and context features."""
        features = {}

        # Home/away
        features['is_home'] = 1.0 if game.home_team_id == game.home_team_id else 0.0  # Simplified

        # Day of week (weekday vs weekend)
        features['is_weekend'] = 1.0 if game.game_date.weekday() >= 5 else 0.0

        # Back-to-back game indicator (simplified)
        features['back_to_back'] = 0.0  # Would need more complex logic

        return features

    def _extract_health_features(
        self,
        prior_games: List[Tuple[PlayerGameStat, Game]],
        current_game: Game
    ) -> Dict[str, float]:
        """Extract health and fatigue features."""
        features = {}

        if len(prior_games) >= 5:
            recent_minutes = [stat.minutes_played for stat, game in prior_games[-5:]]
            features['avg_minutes_recent'] = sum(recent_minutes) / len(recent_minutes)

            # Fatigue indicators
            features['high_minute_games'] = sum(1 for m in recent_minutes if m >= 40)
            features['rest_days'] = 3.0  # Placeholder - would calculate actual rest

        return features

    def _extract_advanced_analytics_features(
        self,
        prior_games: List[Tuple[PlayerGameStat, Game]],
        stat_type: str
    ) -> Dict[str, float]:
        """Extract advanced analytics features."""
        features = {}

        # Simplified advanced metrics
        if len(prior_games) >= 10:
            recent_stats = [stat for stat, game in prior_games[-10:]]

            # Usage rate approximation
            total_minutes = sum(stat.minutes_played for stat in recent_stats)
            total_team_minutes = 48 * 5 * len(recent_stats)  # Rough estimate
            features['usage_rate'] = total_minutes / total_team_minutes if total_team_minutes > 0 else 0

            # Efficiency metrics
            if stat_type == 'points':
                total_pts = sum(stat.points or 0 for stat in recent_stats)
                total_fga = sum(stat.field_goals_attempted or 0 for stat in recent_stats)
                if total_fga > 0:
                    features['shooting_efficiency'] = total_pts / (2 * total_fga)

        return features

    def _extract_situational_features(self, game: Game) -> Dict[str, float]:
        """Extract situational game features."""
        features = {}

        # Game importance (simplified)
        features['game_importance'] = 1.0  # Would analyze playoff implications

        # Competitiveness
        features['close_game'] = 1.0 if abs((game.home_score or 0) - (game.away_score or 0)) <= 10 else 0.0

        return features

    def _extract_stat_value(self, player_stat: PlayerGameStat, stat_type: str) -> float:
        """Extract stat value from player stat object."""
        if stat_type == 'points':
            return player_stat.points or 0
        elif stat_type == 'rebounds':
            return (player_stat.offensive_rebounds or 0) + (player_stat.defensive_rebounds or 0)
        elif stat_type == 'assists':
            return player_stat.assists or 0
        elif stat_type == 'three_pointers_made':
            return player_stat.three_pointers_made or 0
        else:
            return 0

    def train_ensemble_model(
        self,
        player_id: int,
        stat_type: str,
        season_id: Optional[int] = None,
        test_size: float = 0.2
    ) -> Dict[str, float]:
        """
        Train ensemble model for a specific player and stat type.

        Returns:
            Dict with model performance metrics
        """
        try:
            # Build training data
            X, y = self.build_training_dataset(player_id, stat_type, season_id)

            if len(X) < 20:
                return {'error': 'Insufficient training data'}

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train models
            model_predictions = {}
            performance_metrics = {}

            for name, model in self.models.items():
                # Train model
                model.fit(X_train_scaled, y_train)

                # Make predictions
                train_pred = model.predict(X_train_scaled)
                test_pred = model.predict(X_test_scaled)

                # Calculate metrics
                train_mae = mean_absolute_error(y_train, train_pred)
                test_mae = mean_absolute_error(y_test, test_pred)
                train_r2 = r2_score(y_train, train_pred)
                test_r2 = r2_score(y_test, test_pred)

                performance_metrics[name] = {
                    'train_mae': train_mae,
                    'test_mae': test_mae,
                    'train_r2': train_r2,
                    'test_r2': test_r2
                }

                model_predictions[name] = test_pred

            # Calculate ensemble predictions (simple average)
            ensemble_pred = np.mean([pred for pred in model_predictions.values()], axis=0)
            ensemble_mae = mean_absolute_error(y_test, ensemble_pred)
            ensemble_r2 = r2_score(y_test, ensemble_pred)

            performance_metrics['ensemble'] = {
                'mae': ensemble_mae,
                'r2': ensemble_r2
            }

            # Save trained models
            self._save_models(player_id, stat_type)

            return performance_metrics

        except Exception as e:
            return {'error': str(e)}

    def predict_with_ensemble(
        self,
        player_id: int,
        stat_type: str,
        feature_vector: Dict[str, float],
        season_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Make prediction using trained ensemble model.

        Returns:
            Dict with prediction, confidence, and model details
        """
        try:
            # Load models if available
            models_loaded = self._load_models(player_id, stat_type)

            if not models_loaded:
                return {'error': 'No trained models available'}

            # Convert feature vector to DataFrame
            feature_df = pd.DataFrame([feature_vector])

            # Scale features
            feature_scaled = self.scaler.transform(feature_df)

            # Get predictions from each model
            predictions = {}
            for name, model in self.models.items():
                pred = model.predict(feature_scaled)[0]
                predictions[name] = pred

            # Ensemble prediction (weighted average based on recent performance)
            weights = self._calculate_model_weights(player_id, stat_type)
            ensemble_pred = sum(predictions[name] * weights.get(name, 1.0)
                              for name in predictions.keys()) / sum(weights.values())

            # Calculate confidence based on model agreement
            pred_values = list(predictions.values())
            pred_std = statistics.stdev(pred_values) if len(pred_values) > 1 else 0
            confidence = max(0.1, 1.0 - (pred_std / ensemble_pred)) if ensemble_pred > 0 else 0.5

            # Calculate prediction range
            pred_range = {
                'low': max(0, ensemble_pred - pred_std),
                'high': ensemble_pred + pred_std
            }

            return {
                'prediction': round(ensemble_pred, 2),
                'confidence': round(confidence, 3),
                'prediction_range': {k: round(v, 2) for k, v in pred_range.items()},
                'model_predictions': {k: round(v, 2) for k, v in predictions.items()},
                'ensemble_std': round(pred_std, 2)
            }

        except Exception as e:
            return {'error': str(e)}

    def _calculate_model_weights(self, player_id: int, stat_type: str) -> Dict[str, float]:
        """Calculate weights for ensemble based on recent performance."""
        # Default equal weights - could be improved with performance tracking
        return {name: 1.0 for name in self.models.keys()}

    def _save_models(self, player_id: int, stat_type: str):
        """Save trained models to disk."""
        model_path = f"{self.models_dir}/{player_id}_{stat_type}_models.pkl"
        scaler_path = f"{self.models_dir}/{player_id}_{stat_type}_scaler.pkl"

        try:
            with open(model_path, 'wb') as f:
                pickle.dump(self.models, f)

            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
        except Exception as e:
            print(f"Warning: Could not save models: {e}")

    def _load_models(self, player_id: int, stat_type: str) -> bool:
        """Load trained models from disk."""
        model_path = f"{self.models_dir}/{player_id}_{stat_type}_models.pkl"
        scaler_path = f"{self.models_dir}/{player_id}_{stat_type}_scaler.pkl"

        try:
            with open(model_path, 'rb') as f:
                self.models = pickle.load(f)

            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)

            return True
        except:
            return False

    def get_model_performance_summary(self) -> Dict[str, Any]:
        """Get overall model performance summary."""
        return {
            'models_available': list(self.models.keys()),
            'feature_importance': self.feature_importance,
            'model_performance': self.model_performance
        }