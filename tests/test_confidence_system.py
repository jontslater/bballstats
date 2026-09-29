#!/usr/bin/env python3
"""
Unit tests for calibrated probability and confidence systems.

Usage:
    PYTHONPATH=backend python tests/test_confidence_system.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import unittest
from app.services.calibrated_probability import CalibratedProbabilityCalculator
from app.services.confidence_calculator import ConfidenceCalculator
from app.services.bet_definitions import BetDefinitions


class TestCalibratedProbability(unittest.TestCase):
    """Test calibrated probability calculator."""
    
    def setUp(self):
        self.calc = CalibratedProbabilityCalculator(sport='NBA')
    
    def test_probability_for_line_small_sample(self):
        """Test probability calculation with small sample (uses Student-t)."""
        result = self.calc.calculate_probability_for_line(
            line=20.0,
            player_mean=25.0,
            player_std=5.0,
            sample_size=10,
            stat_type='points'
        )
        
        self.assertIn('probability', result)
        self.assertGreater(result['probability'], 0.5)  # Should be >50% to exceed 20 when mean is 25
        self.assertLess(result['probability'], 1.0)
        self.assertEqual(result['effective_n'], 10)
    
    def test_probability_for_line_large_sample(self):
        """Test probability calculation with large sample (uses Normal dist)."""
        result = self.calc.calculate_probability_for_line(
            line=20.0,
            player_mean=25.0,
            player_std=5.0,
            sample_size=50,
            stat_type='points'
        )
        
        self.assertIn('probability', result)
        self.assertGreater(result['probability'], 0.5)
        self.assertLess(result['probability'], 1.0)
    
    def test_shrinkage_toward_prior(self):
        """Test Empirical Bayes shrinkage."""
        calc = CalibratedProbabilityCalculator(sport='NBA')
        
        # Small sample: should shrink heavily toward league mean
        result_small = calc.calculate_probability_for_line(
            line=20.0,
            player_mean=30.0,  # Player seems good
            player_std=5.0,
            sample_size=5,  # But only 5 games
            stat_type='points',
            league_mean=22.0,  # League average
            league_std=6.0
        )
        
        # Shrunk mean should be between player mean (30) and league mean (22)
        self.assertGreater(result_small['shrunk_mean'], 22.0)
        self.assertLess(result_small['shrunk_mean'], 30.0)
    
    def test_determine_line_real_vs_synthetic(self):
        """Test line determination with real vs synthetic lines."""
        # Real line
        result_real = self.calc.determine_line_from_distribution(
            player_mean=25.0,
            player_std=5.0,
            sample_size=20,
            stat_type='points',
            real_line=23.5
        )
        
        self.assertEqual(result_real['line'], 23.5)
        self.assertEqual(result_real['line_source'], 'sportsbook')
        self.assertFalse(result_real['is_synthetic'])
        
        # Synthetic line
        result_synthetic = self.calc.determine_line_from_distribution(
            player_mean=25.0,
            player_std=5.0,
            sample_size=20,
            stat_type='points',
            real_line=None
        )
        
        self.assertAlmostEqual(result_synthetic['line'], 25.0, delta=0.5)
        self.assertEqual(result_synthetic['line_source'], 'model')
        self.assertTrue(result_synthetic['is_synthetic'])


class TestConfidenceCalculator(unittest.TestCase):
    """Test confidence tier calculator."""
    
    def setUp(self):
        self.calc = ConfidenceCalculator(sport='NBA')
    
    def test_high_confidence_real_line(self):
        """Test HIGH confidence with large sample and real line."""
        result = self.calc.calculate_confidence(
            sample_size=35,
            line_source='sportsbook',
            coefficient_of_variation=0.20,
            is_synthetic_line=False,
            has_real_line=True
        )
        
        self.assertEqual(result['tier'], 'HIGH')
        self.assertGreater(result['score'], 50)  # Log scale: 35 games → ~55-60 pts
    
    def test_synthetic_line_capped_at_low(self):
        """Test that synthetic lines are capped at LOW confidence."""
        result = self.calc.calculate_confidence(
            sample_size=40,  # Would normally be HIGH
            line_source='model',
            is_synthetic_line=True,
            has_real_line=False
        )
        
        # Should be capped at LOW even with large sample
        self.assertIn(result['tier'], ['LOW', 'MODEL_ONLY'])
    
    def test_nfl_thresholds(self):
        """Test NFL-specific sample size thresholds."""
        calc_nfl = ConfidenceCalculator(sport='NFL')
        
        # 20 games should be HIGH for NFL
        result = calc_nfl.calculate_confidence(
            sample_size=20,
            line_source='sportsbook',
            is_synthetic_line=False,
            has_real_line=True
        )
        
        self.assertEqual(result['tier'], 'HIGH')
    
    def test_combo_confidence(self):
        """Test combo confidence calculation."""
        conf1 = {
            'tier': 'HIGH',
            'score': 90,
            'reasons': ['30 games']
        }
        conf2 = {
            'tier': 'MEDIUM',
            'score': 70,
            'reasons': ['20 games']
        }
        
        result = self.calc.calculate_combo_confidence([conf1, conf2])
        
        # Should take minimum tier
        self.assertEqual(result['tier'], 'MEDIUM')
        # Should average scores
        self.assertAlmostEqual(result['score'], 80.0, delta=1.0)


class TestBetDefinitions(unittest.TestCase):
    """Test bet line calculations."""
    
    def setUp(self):
        self.bet_defs = BetDefinitions(sport='NBA')
    
    def test_calculate_bet_lines_with_real_line(self):
        """Test bet line calculation with real sportsbook line."""
        result = self.bet_defs.calculate_bet_lines(
            adjusted_mean=25.0,
            adjusted_std=5.0,
            sample_size=30,
            stat_type='points',
            real_line=23.5
        )
        
        self.assertEqual(result['standard_line'], 23.5)
        self.assertEqual(result['line_source'], 'sportsbook')
        self.assertFalse(result['is_synthetic'])
        
        # Safe line should be lower
        self.assertLess(result['safe_line'], result['standard_line'])
        # Long shot should be higher
        self.assertGreater(result['long_shot_line'], result['standard_line'])
        
        # Probabilities should be reasonable
        self.assertGreater(result['safe_probability'], result['standard_probability'])
        self.assertGreater(result['standard_probability'], result['long_shot_probability'])
    
    def test_calculate_bet_lines_synthetic(self):
        """Test bet line calculation with synthetic line."""
        result = self.bet_defs.calculate_bet_lines(
            adjusted_mean=25.0,
            adjusted_std=5.0,
            sample_size=30,
            stat_type='points',
            real_line=None
        )
        
        self.assertEqual(result['line_source'], 'model')
        self.assertTrue(result['is_synthetic'])
        # Standard line should be near the mean
        self.assertAlmostEqual(result['standard_line'], 25.0, delta=0.5)
    
    def test_no_flat_probabilities(self):
        """Test that we don't get flat 0.75/0.60/0.25 probabilities."""
        result = self.bet_defs.calculate_bet_lines(
            adjusted_mean=25.0,
            adjusted_std=5.0,
            sample_size=30,
            stat_type='points',
            real_line=None
        )
        
        # Should not equal flat fallback values
        self.assertNotEqual(result['safe_probability'], 0.75)
        self.assertNotEqual(result['standard_probability'], 0.60)
        self.assertNotEqual(result['long_shot_probability'], 0.25)
    
    def test_determine_bet_type(self):
        """Test bet type determination with new likelihood-based logic."""
        # Safe bet: safe_probability >= standard_probability
        bet_type = self.bet_defs.determine_bet_type(
            safe_probability=0.70,
            standard_probability=0.52,
            long_shot_probability=0.18
        )
        self.assertEqual(bet_type, 'safe')
        
        # Safe bet: even modest probability (0.60 >= 0.50)
        bet_type = self.bet_defs.determine_bet_type(
            safe_probability=0.60,
            standard_probability=0.50,
            long_shot_probability=0.15
        )
        self.assertEqual(bet_type, 'safe')  # Changed: safe = highest likelihood
        
        # Standard bet: standard better than safe, and >= 0.40
        bet_type = self.bet_defs.determine_bet_type(
            safe_probability=0.35,
            standard_probability=0.45,
            long_shot_probability=0.15
        )
        self.assertEqual(bet_type, 'standard')
        
        # Long shot: lower probability in 0.10-0.35 range
        bet_type = self.bet_defs.determine_bet_type(
            safe_probability=0.30,
            standard_probability=0.35,
            long_shot_probability=0.20
        )
        self.assertEqual(bet_type, 'long_shot')
        
        # Pass
        bet_type = self.bet_defs.determine_bet_type(
            safe_probability=0.50,
            standard_probability=0.35,
            long_shot_probability=0.05
        )
        self.assertEqual(bet_type, 'pass')


if __name__ == '__main__':
    # Run tests
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with error code if tests failed
    sys.exit(0 if result.wasSuccessful() else 1)
