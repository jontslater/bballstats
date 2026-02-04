# Prediction Accuracy Improvements

## Overview
Systematic improvements to prediction accuracy, focusing on Poor Man's Bet suggestions to help turn $5 into $1000.

## ✅ Completed Improvements

### 1. Probability Calibration System
**Problem**: Predicted probabilities weren't matching actual hit rates. If we predicted 75%, it might only hit 65%.

**Solution**: 
- Created `PredictionCalibration` service to track actual vs predicted outcomes
- Calculates calibration curves by probability ranges (e.g., 70-75%, 75-80%)
- Automatically adjusts probabilities based on historical accuracy
- Integrated into prediction generation

**Files**:
- `backend/app/services/prediction_calibration.py` - Calibration service
- `backend/app/services/bet_definitions.py` - Updated to use calibration
- `backend/app/services/prediction_service.py` - Integrated calibration

**Usage**:
```bash
# Update predictions with actual results (run after games finish)
python scripts/update_prediction_results.py

# View calibration statistics
python scripts/update_prediction_results.py --show-curves
```

### 2. Enhanced Poor Man's Bet Filtering
**Problem**: Suggestions weren't prioritizing the most reliable predictions.

**Solution**:
- Multi-tier priority system:
  1. **Priority 1**: Sample size 30+, LOW volatility, 80%+ probability
  2. **Priority 2**: Sample size 20+, LOW volatility
  3. **Priority 3**: Sample size 20+, MEDIUM volatility (if needed)
  4. **Priority 4**: Sample size 15+, MEDIUM volatility (fallback)
- Enhanced sorting: LOW volatility > Higher sample size > Higher probability
- Filters out injured/questionable players

**Impact**: Should see more reliable suggestions with better hit rates.

**Files**:
- `backend/app/services/poor_mans_bet_service.py` - Enhanced `_find_safest_bets()`

### 3. Validation & Feedback Loop
**Problem**: No way to track if predictions were accurate.

**Solution**:
- Script to update predictions with actual game results
- Calculates hit rates vs predicted probabilities
- Shows calibration statistics (over/under-confidence)
- Stores actual results in database for future learning

**Usage**:
```bash
# After games finish, update results
python scripts/update_prediction_results.py --date 2026-01-05

# View statistics
python scripts/update_prediction_results.py --show-curves
```

## 🔄 Next Steps (In Progress)

### 4. ML Factor Weight Optimization
**Goal**: Learn which adjustment factors matter most for accuracy.

**Approach**:
- Use `MLOptimizer` to analyze historical predictions
- Train model to find optimal weights for factors:
  - Minutes factor (currently 1.0-1.2x)
  - Defense factor (currently 0.9-1.1x)
  - Form trend (currently 0.95-1.05x)
  - Home/away, rest days, etc.
- Replace equal multiplication with weighted combination

**Status**: Pending

### 5. Improved Recent Form Weighting
**Goal**: Give more weight to recent games vs older games.

**Current**: Uses last 15-20 games with equal weight.

**Proposed**: 
- Exponential decay weighting (last game = 1.0x, 3 games ago = 0.8x, 10 games ago = 0.5x)
- Focus on last 5-10 games for trend analysis
- More accurate for players in good/bad form streaks

**Status**: Pending

### 6. Enhanced Parlay Selection
**Goal**: Better diversify parlays and optimize probability combinations.

**Current**: Greedy selection, prefers different players/games.

**Proposed**:
- Consider correlation between players (same game, same team)
- Optimize for maximum combined probability
- Better handling of edge cases

**Status**: Pending

## 📊 Monitoring & Validation

### How to Track Improvement

1. **Run calibration updates regularly**:
   ```bash
   # After each day's games finish
   python scripts/update_prediction_results.py
   ```

2. **Check calibration statistics**:
   ```bash
   python scripts/update_prediction_results.py --show-curves
   ```

3. **Monitor Poor Man's Bet success rate**:
   - Track actual hit rate of suggestions
   - Compare to predicted probabilities
   - Should see improvement over time

### Target Metrics

- **Safe bets (75% predicted)**: Should hit ~75% of the time
- **Calibration error**: <5% difference between predicted and actual
- **Poor Man's Bet**: Consistent suggestions with high reliability

## 🔧 Technical Details

### Calibration Data Structure
Calibration curves are calculated by probability ranges:
```python
{
    'safe': {
        '70-75': {
            'sample_size': 150,
            'predicted_probability': 0.73,
            'actual_hit_rate': 0.70,
            'calibration_adjustment': -0.03  # Adjust down by 3%
        },
        ...
    }
}
```

### Prediction Update Process
1. Games finish → Stats collected
2. Run `update_prediction_results.py`
3. Script matches predictions to actual stats
4. Updates `actual_result`, `hit_safe`, `hit_standard`, `hit_long_shot`
5. Calibration curves recalculated
6. Future predictions use calibrated probabilities

## 🎯 Expected Impact

- **Immediate**: Better filtering = higher quality Poor Man's Bet suggestions
- **Short-term (1-2 weeks)**: Calibration data accumulates, probabilities become more accurate
- **Long-term (1+ month)**: ML optimization learns optimal factor weights, further improves accuracy

The goal: Turn $5 into $1000 through consistent, reliable betting suggestions with accurate probabilities.

