#!/usr/bin/env python3
"""
Standalone unit tests for calibrated probability and confidence systems.
Tests the core logic without database dependencies.
"""
import sys
import unittest
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import only the new modules (avoid app.__init__ which loads all services)
import importlib.util

def load_module(module_name, file_path):
    """Load a module from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load modules directly
calibrated_prob = load_module(
    'calibrated_probability',
    backend_path / 'app' / 'services' / 'calibrated_probability.py'
)
confidence_calc_module = load_module(
    'confidence_calculator',
    backend_path / 'app' / 'services' / 'confidence_calculator.py'
)

CalibratedProbabilityCalculator = calibrated_prob.CalibratedProbabilityCalculator
ConfidenceCalculator = confidence_calc_module.ConfidenceCalculator


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
        print(f"✓ Small sample probability: {result['probability']:.3f}")
    
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
        print(f"✓ Large sample probability: {result['probability']:.3f}")
    
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
        print(f"✓ Shrinkage: player_mean=30.0 → shrunk_mean={result_small['shrunk_mean']:.1f} (toward league_mean=22.0)")
    
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
        print(f"✓ Real line: {result_real['line']} (source: {result_real['line_source']})")
        
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
        print(f"✓ Synthetic line: {result_synthetic['line']} (source: {result_synthetic['line_source']})")


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
        self.assertGreater(result['score'], 80)
        print(f"✓ HIGH confidence: tier={result['tier']}, score={result['score']:.1f}")
    
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
        print(f"✓ Synthetic line capped: tier={result['tier']} (despite sample_size=40)")
    
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
        print(f"✓ NFL thresholds: 20 games → {result['tier']} confidence")
    
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
        print(f"✓ Combo confidence: MIN(HIGH, MEDIUM) = {result['tier']}, avg_score={result['score']:.1f}")


if __name__ == '__main__':
    print("=" * 60)
    print("Testing Calibrated Probability & Confidence System")
    print("=" * 60)
    print()
    
    # Run tests
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)
    
    # Exit with error code if tests failed
    sys.exit(0 if result.wasSuccessful() else 1)
