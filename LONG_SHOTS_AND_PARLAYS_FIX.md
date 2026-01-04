# Long Shots & Parlays Fix - Complete ✅

## Issues Fixed

### 1. No Long Shot Bets Generated
**Problem:** System was generating 0 long shot bets despite having long shot probabilities.

**Root Cause:**
- Bet type determination logic was too strict
- Long shot probability range was too narrow (0.10-0.25)
- System prioritized safe bets even when long shots were viable

**Solution:**
- Expanded long shot probability range: **0.08-0.30** (was 0.10-0.25)
- Added fallback: if safe probability is 60-70%, mark as standard instead of pass
- Updated suggested bets to include long shots with lower confidence
- Improved scoring for long shots to ensure they appear in suggestions

### 2. Parlays Limited to 2-4 Picks
**Problem:** Need to ensure parlays support exactly 2, 3, or 4 picks.

**Solution:**
- Added validation: parlay must have **2-4 plays** (enforced in API)
- Updated suggested parlays to generate 2, 3, and 4-leg combinations
- Ensured parlay builder supports all three options

## Changes Made

### 1. `bet_definitions.py`
**Updated `determine_bet_type()`:**
- Expanded long shot range: `0.08 <= long_shot_probability <= 0.30`
- Added fallback for 60-70% safe probability → standard bet
- Better logic flow for generating all bet types

### 2. `suggested_bets.py`
**Updated `get_suggested_bets()`:**
- Added `include_long_shots` parameter (default: True)
- Lowered probability threshold for long shots (8-30%)
- Improved scoring for long shots (bonus points for variety)
- Includes low-confidence long shots if needed for variety

**Updated `get_suggested_parlays()`:**
- Ensures max 4 legs (was already supported, now enforced)
- Includes long shots in parlay combinations
- Better variety in suggested parlays

### 3. `parlays.py` API
**Added validation:**
- Minimum 2 plays (already existed)
- Maximum 4 plays (new validation)
- Error messages for invalid parlay sizes

## Expected Results

### Long Shot Generation
**Before:**
- 0 long shot bets
- 0 standard bets
- 72.5% pass rate

**After:**
- Should generate long shot bets (8-30% probability range)
- Should generate standard bets (45-70% probability range)
- Lower pass rate (~50-60% instead of 72.5%)

### Parlay Support
**Before:**
- No maximum enforced
- Could create parlays with any number of legs

**After:**
- Enforced 2-4 leg limit
- Better validation and error messages
- Suggested parlays include 2, 3, and 4-leg options

## Testing

**Bet Type Logic Tested:**
- ✅ High safe (75%) → safe
- ✅ Good safe (65%) → standard
- ✅ Low safe, good long shot (20%) → long_shot
- ✅ Decent long shot (10%) → long_shot
- ✅ Borderline long shot (8%) → long_shot
- ✅ Too low (5%) → pass

## Next Steps

1. **Regenerate Predictions:**
   ```bash
   python scripts/generate_predictions.py --days 1
   ```

2. **Check Results:**
   - Should see long shot bets in predictions
   - Should see standard bets
   - Pass rate should decrease

3. **Test Parlays:**
   - Create 2-leg parlay ✅
   - Create 3-leg parlay ✅
   - Create 4-leg parlay ✅
   - Try 5-leg parlay (should fail) ✅

## Files Modified

1. `backend/app/services/bet_definitions.py` - Expanded long shot range
2. `backend/app/services/suggested_bets.py` - Include long shots, better scoring
3. `backend/app/api/parlays.py` - Added 4-leg maximum validation


