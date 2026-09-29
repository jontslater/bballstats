"""
Bet Definitions

Defines safe, standard, and long shot bet lines and probabilities using calibrated methods.
"""
from typing import Dict, Optional
from app.services.calibrated_probability import CalibratedProbabilityCalculator


class BetDefinitions:
    """Define bet types and calculate lines/probabilities using calibrated methods."""
    
    def __init__(self, sport: str = 'NBA'):
        """
        Initialize with sport-specific configuration.
        
        Args:
            sport: Sport type ('NBA', 'NFL', or 'MLB')
        """
        self.sport = sport
        self.calibrator = CalibratedProbabilityCalculator(sport)
    
    def calculate_bet_lines(
        self,
        adjusted_mean: float,
        adjusted_std: float,
        sample_size: int,
        stat_type: str,
        real_line: Optional[float] = None,
        league_mean: Optional[float] = None,
        league_std: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calculate bet lines and calibrated probabilities.
        
        Strategy:
        1. Determine target line (real if available, else synthetic from mean)
        2. Generate candidate lines on discrete grid (0.5, 1.5, 2.5, ... for counts)
        3. Calculate calibrated probability for each candidate
        4. Choose safe = line with HIGHEST probability (not requiring p>=0.65)
        5. Choose long_shot = line with p in 0.15-0.30 range, capped at plausible max
        6. Standard = real line or mean-based line
        
        Safe picks are NOT "sure things" - they're just the highest-likelihood option.
        Ranking by edge and sample size will differentiate quality.
        Thin-sample picks are flagged via tier/reasons, not hidden.
        
        Args:
            adjusted_mean: Adjusted mean (μ) after all adjustments
            adjusted_std: Adjusted standard deviation (σ)
            sample_size: Number of games in history
            stat_type: Type of stat (e.g., 'points', 'passing_yards')
            real_line: Real sportsbook line (if available)
            league_mean: League average for this stat
            league_std: League standard deviation
        
        Returns:
            Dict with lines, probabilities, and metadata
        """
        # Determine standard/target line
        if real_line is not None and real_line > 0:
            standard_line = real_line
            line_source = 'sportsbook'
            is_synthetic = False
        else:
            # Shrink mean if league data available
            if league_mean is not None:
                shrunk_mean, _ = self.calibrator._shrink_mean_toward_prior(
                    adjusted_mean, league_mean, sample_size
                )
            else:
                shrunk_mean = adjusted_mean
            
            # Round to nearest half-integer for discrete grid
            standard_line = round(shrunk_mean * 2) / 2
            
            # Ensure minimum sensible line per stat type
            min_line = {
                'home_runs': 0.5,
                'hits': 0.5,
                'total_bases': 0.5,
                'strikeouts': 0.5,
                'rbis': 0.5
            }
            if self.sport == 'MLB':
                stat_min = min_line.get(stat_type, 0.5)
                standard_line = max(standard_line, stat_min)
                
                # Avoid whole-number (x.0) OVER lines for hits/TB/RBIs
                # Use x.5 lines instead for better granularity
                if stat_type in ['hits', 'total_bases', 'rbis']:
                    if standard_line > 0 and standard_line % 1.0 == 0:
                        standard_line += 0.5
            
            line_source = 'model'
            is_synthetic = True
        
        # Calculate probability for standard line
        standard_data = self.calibrator.calculate_probability_for_line(
            standard_line, adjusted_mean, adjusted_std, sample_size, stat_type,
            league_mean, league_std
        )
        
        # Generate candidate lines on discrete grid
        # Range: 0.5 to reasonable max for this stat type
        max_candidate = self._get_max_line_for_stat(stat_type, adjusted_mean)
        candidates = [x * 0.5 for x in range(1, int(max_candidate * 2) + 1)]
        
        # Ensure minimum line is 0.5
        candidates = [c for c in candidates if c >= 0.5]
        
        # Find safe line: highest line with best probability (not requiring p>=0.65)
        # Safe = highest probability pick, even if not a "sure thing"
        safe_line = None
        safe_probability = None
        best_safe_prob = 0.0
        
        for line in sorted(candidates):
            if line > standard_line * 0.8:  # Safe should be easier than standard
                continue
            
            prob_data = self.calibrator.calculate_probability_for_line(
                line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            
            # Track the line with highest probability (safe = highest likelihood)
            if prob_data['probability'] > best_safe_prob:
                best_safe_prob = prob_data['probability']
                safe_line = line
                safe_probability = prob_data['probability']
        
        # If no safe line found, use lowest candidate
        if safe_line is None:
            safe_line = min(candidates) if candidates else 0.5
            safe_data = self.calibrator.calculate_probability_for_line(
                safe_line, adjusted_mean, adjusted_std, sample_size, stat_type,
                league_mean, league_std
            )
            safe_probability = safe_data['probability']
        
        # Find long shot line: line with p in 0.15-0.30 range (prefer ~0.20)
        # Cap at sport-specific single-game maximum
        # Prefer x.5 lines for OVER bets (avoid whole numbers like 1.0, 2.0, 3.0)
        long_shot_max = self._get_long_shot_max_for_stat(stat_type)
        long_shot_line = None
        long_shot_probability = None
        best_distance = float('inf')
        target_prob = 0.20
        
        # For HR, if probability would be <5%, skip long_shot tier entirely
        if self.sport == 'MLB' and stat_type == 'home_runs':
            # Check if even the lowest long_shot candidate would be <5%
            test_line = standard_line + 0.5
            if test_line <= long_shot_max:
                test_prob = self.calibrator.calculate_probability_for_line(
                    test_line, adjusted_mean, adjusted_std, sample_size, stat_type,
                    league_mean, league_std
                )
                if test_prob['probability'] < 0.05:
                    # Skip HR long_shot entirely - too unlikely
                    long_shot_line = None
                    long_shot_probability = None
                    best_distance = float('inf')
        
        if long_shot_line is None:
            for line in candidates:
                if line <= standard_line:
                    continue  # Long shot should be harder than standard
                if line > long_shot_max:
                    continue  # Cap at plausible single-game maximum
                
                # Prefer x.5 lines (skip whole numbers for MLB count stats)
                if self.sport == 'MLB' and stat_type in ['hits', 'total_bases', 'home_runs']:
                    if line > 0 and line % 1.0 == 0:
                        continue  # Skip whole-number lines like 1.0, 2.0, 3.0
                
                prob_data = self.calibrator.calculate_probability_for_line(
                    line, adjusted_mean, adjusted_std, sample_size, stat_type,
                    league_mean, league_std
                )
                prob = prob_data['probability']
                
                if 0.15 <= prob <= 0.30:
                    distance = abs(prob - target_prob)
                    if distance < best_distance:
                        best_distance = distance
                        long_shot_line = line
                        long_shot_probability = prob
        
        # If no long shot found in probability range or exceeds max, don't force one
        # CRITICAL: Do NOT fall back to auto-generating a long_shot line when probability is too low
        # If long_shot_line is None here, it means no valid long_shot exists - leave it None
        if long_shot_line is None:
            # No valid long_shot found (either out of p range or above max line)
            # Do NOT force a fallback line - keep it None
            long_shot_probability = None
        
        return {
            'safe_line': round(safe_line, 1),
            'safe_probability': safe_probability,
            'standard_line': round(standard_line, 1),
            'standard_probability': standard_data['probability'],
            'long_shot_line': round(long_shot_line, 1) if long_shot_line is not None else None,
            'long_shot_probability': long_shot_probability,
            'line_source': line_source,
            'is_synthetic': is_synthetic,
            'shrunk_mean': standard_data['shrunk_mean'],
            'effective_std': standard_data['effective_std'],
            'effective_n': standard_data['effective_n']
        }
    
    @staticmethod
    def determine_bet_type(
        safe_probability: float,
        standard_probability: float,
        long_shot_probability: float
    ) -> str:
        """
        Determine recommended bet type based on calibrated probabilities.
        
        Returns 'pass' if all probabilities are too low (best < 0.45).
        Long shots allowed even if best < 0.45 (they're intentionally risky).
        
        Returns:
            'safe', 'standard', 'long_shot', or 'pass'
        """
        # Long shots: check first (allowed even if best_prob < 0.45)
        if 0.10 <= long_shot_probability <= 0.35:
            # Long shot qualifies if it's the best option
            if long_shot_probability >= safe_probability and long_shot_probability >= standard_probability:
                return 'long_shot'
        
        # If all probabilities are poor, pass (unless long_shot already qualified)
        best_prob = max(safe_probability, standard_probability, long_shot_probability)
        if best_prob < 0.45:
            return 'pass'
        
        # Safe bets: highest likelihood if >= standard
        if safe_probability >= standard_probability and safe_probability >= 0.45:
            return 'safe'
        
        # Standard bets: moderate probability
        if standard_probability >= 0.45:
            return 'standard'
        
        # Default to pass if nothing qualifies
        return 'pass'
    
    def _get_max_line_for_stat(self, stat_type: str, mean: float) -> float:
        """Get reasonable maximum line for candidate generation."""
        if self.sport == 'MLB':
            mlb_maxes = {
                'hits': 5.0,  # Very high for a single game
                'home_runs': 3.0,  # 3 HRs is exceptional
                'total_bases': 10.0,  # 3 HRs = 12 bases, but 10 is reasonable max
                'rbis': 8.0,
                'strikeouts': 15.0,  # For pitchers
            }
            return mlb_maxes.get(stat_type, max(mean * 3, 10.0))
        elif self.sport == 'NFL':
            nfl_maxes = {
                'passing_yards': 450.0,
                'rushing_yards': 200.0,
                'receiving_yards': 200.0,
                'receptions': 15.0,
                'passing_tds': 5.0,
                'rushing_tds': 4.0,
                'receiving_tds': 3.0,
            }
            return nfl_maxes.get(stat_type, max(mean * 3, 20.0))
        else:  # NBA
            nba_maxes = {
                'points': 60.0,
                'rebounds': 25.0,
                'assists': 20.0,
                'three_pointers_made': 12.0,
            }
            return nba_maxes.get(stat_type, max(mean * 3, 30.0))
    
    def _get_long_shot_max_for_stat(self, stat_type: str) -> float:
        """Get plausible single-game maximum for long-shot lines."""
        if self.sport == 'MLB':
            mlb_long_shot_maxes = {
                'hits': 2.5,  # 3+ hits in a game is rare
                'home_runs': 1.5,  # 2+ HRs is a long shot
                'total_bases': 4.5,  # 5+ bases is exceptional
                'rbis': 4.5,  # 5+ RBI is a long shot
                'strikeouts': 10.5,  # For pitchers
            }
            return mlb_long_shot_maxes.get(stat_type, 10.0)
        elif self.sport == 'NFL':
            nfl_long_shot_maxes = {
                'passing_yards': 350.0,
                'rushing_yards': 150.0,
                'receiving_yards': 150.0,
                'receptions': 12.0,
                'passing_tds': 4.0,
                'rushing_tds': 3.0,
                'receiving_tds': 2.5,
            }
            return nfl_long_shot_maxes.get(stat_type, 200.0)
        else:  # NBA
            nba_long_shot_maxes = {
                'points': 45.0,
                'rebounds': 18.0,
                'assists': 15.0,
                'three_pointers_made': 9.0,
            }
            return nba_long_shot_maxes.get(stat_type, 40.0)
