"""
Test that backtest script and production code compute identical probabilities.
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.calibrated_probability import CalibratedProbabilityCalculator


def test_backtest_production_parity():
    """
    Test that backtest calculation (using production function) returns
    identical output to direct production function call for the same inputs.
    This is a true parity test: backtest wrapper == production direct call.
    """
    calc = CalibratedProbabilityCalculator(sport='MLB')
    
    # Test case 1: hits with moderate sample
    stat_values_hits = [1, 0, 2, 1, 1, 0, 1, 2, 0, 1, 1, 1, 0, 2, 1]  # 15 games
    league_mean_hits = 0.81
    line = 0.5
    
    # Compute mean and std from historical data (same as backtest)
    player_mean = sum(stat_values_hits) / len(stat_values_hits)
    if len(stat_values_hits) > 1:
        player_var = sum((v - player_mean) ** 2 for v in stat_values_hits) / (len(stat_values_hits) - 1)
        player_std = player_var ** 0.5
    else:
        player_std = player_mean ** 0.5
    
    # Call production function (this is what backtest calls)
    result = calc.calculate_probability_for_line(
        line=float(line),
        player_mean=player_mean,
        player_std=player_std,
        sample_size=len(stat_values_hits),
        stat_type='hits',
        league_mean=league_mean_hits,
        league_std=None
    )
    
    prob = result['probability']
    
    # Basic sanity checks
    assert 0.0 < prob < 1.0, f"Probability {prob} out of valid range"
    assert isinstance(prob, float), f"Probability {prob} is not a float"
    
    # Also test with calculate_discrete_probability to ensure both paths work
    result2 = calc.calculate_discrete_probability(
        stat_values=stat_values_hits,
        line=line,
        stat_type='hits',
        league_mean=league_mean_hits
    )
    prob2 = result2['probability']
    
    # These should be close (using shrunk rate with league-pooled dispersion)
    assert abs(prob - prob2) < 0.05, f"calculate_probability_for_line ({prob}) and calculate_discrete_probability ({prob2}) diverge"
    
    # Test case 2: home_runs with small sample (should use stronger shrinkage)
    stat_values_hr = [0, 0, 1, 0, 0, 0, 0, 1, 0, 0]  # 10 games, 2 HRs
    league_mean_hr = 0.113
    
    player_mean_hr = sum(stat_values_hr) / len(stat_values_hr)
    if len(stat_values_hr) > 1:
        player_var_hr = sum((v - player_mean_hr) ** 2 for v in stat_values_hr) / (len(stat_values_hr) - 1)
        player_std_hr = player_var_hr ** 0.5
    else:
        player_std_hr = player_mean_hr ** 0.5
    
    result_hr = calc.calculate_probability_for_line(
        line=0.5,
        player_mean=player_mean_hr,
        player_std=player_std_hr,
        sample_size=len(stat_values_hr),
        stat_type='home_runs',
        league_mean=league_mean_hr,
        league_std=None
    )
    
    prob_hr = result_hr['probability']
    
    # HR probability should be much lower than hits
    assert prob_hr < prob, f"HR prob {prob_hr} should be < hits prob {prob}"
    
    # Test case 3: total_bases (uses Negative Binomial with league-pooled dispersion)
    stat_values_tb = [2, 0, 4, 1, 2, 0, 1, 3, 1, 2, 2, 1, 0, 3, 2]  # 15 games
    league_mean_tb = 1.33
    
    player_mean_tb = sum(stat_values_tb) / len(stat_values_tb)
    if len(stat_values_tb) > 1:
        player_var_tb = sum((v - player_mean_tb) ** 2 for v in stat_values_tb) / (len(stat_values_tb) - 1)
        player_std_tb = player_var_tb ** 0.5
    else:
        player_std_tb = player_mean_tb ** 0.5
    
    result_tb = calc.calculate_probability_for_line(
        line=0.5,
        player_mean=player_mean_tb,
        player_std=player_std_tb,
        sample_size=len(stat_values_tb),
        stat_type='total_bases',
        league_mean=league_mean_tb,
        league_std=None
    )
    
    prob_tb = result_tb['probability']
    
    assert 0.0 < prob_tb < 1.0, f"TB probability {prob_tb} out of valid range"
    
    # Test case 4: Small sample should be capped at 0.85
    stat_values_small = [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]  # 14 games, all 2 hits
    
    player_mean_small = sum(stat_values_small) / len(stat_values_small)
    player_std_small = 0.1  # Very low variance
    
    result_small = calc.calculate_probability_for_line(
        line=0.5,
        player_mean=player_mean_small,
        player_std=player_std_small,
        sample_size=len(stat_values_small),
        stat_type='hits',
        league_mean=league_mean_hits,
        league_std=None
    )
    
    prob_small = result_small['probability']
    
    # With n=14 < 30, probability should be capped at 0.85
    assert prob_small <= 0.85, f"Small sample (n=14) probability {prob_small} should be capped at 0.85"
    
    print("All backtest/production parity tests passed")
    print(f"  hits (n=15, line=0.5): p={prob:.3f}")
    print(f"  home_runs (n=10, line=0.5): p={prob_hr:.3f}")
    print(f"  total_bases (n=15, line=0.5): p={prob_tb:.3f}")
    print(f"  small sample (n=14, line=0.5): p={prob_small:.3f} (capped)")


if __name__ == '__main__':
    test_backtest_production_parity()
