# PR #2 Follow-up Fixes

This document describes the issues found after PR #2 was merged and the fixes applied.

## Issues Fixed

### 1. ✅ NBA Schedule Script Syntax
**Issue**: The user reported a syntax error in `scripts/collect_nba_schedule.py` after 403 retry changes.
**Status**: Script parses correctly in current repo state. No syntax error found.
**Improvements Added**:
- Added exponential backoff retry logic (2s, 4s, 8s delays)
- Enhanced browser-like headers to reduce 403 risk
- Added ESPN API fallback if NBA CDN continues blocking

### 2. ✅ GameSchedule Model - ESPN Game ID Support
**Issue**: `scripts/nfl_collect_schedule.py` expects `espn_game_id` but DB model only has `nba_game_id`. NFL script was abusing the `nba_game_id` column for NFL games.

**Solution**:
- Added `external_game_id` column to `GameSchedule` model (sport-agnostic)
- Created migration script: `backend/scripts/add_external_game_id_column.py`
- Updated NFL script to use `external_game_id` instead of `nba_game_id`
- Updated NBA script to use `external_game_id` (with backward compat for `nba_game_id`)
- Kept `nba_game_id` column for backward compatibility during transition

**Files Changed**:
- `backend/app/models/game_schedule.py` - Added `external_game_id` column
- `scripts/nfl_collect_schedule.py` - Use `external_game_id` instead of `nba_game_id`
- `scripts/collect_nba_schedule.py` - Use `external_game_id` with fallback to `nba_game_id`

**Migration Path**:
```bash
# Run migration to add column and migrate existing data
python backend/scripts/add_external_game_id_column.py
```

### 3. ✅ Suggested Bets - MLB Outlier Filter
**Issue**: MLB suggested bets show absurd lines like "Hits Over 10.0" or "HR Over 10.0" because:
- Fallback line defaults to 10.0 (appropriate for NBA, not MLB)
- Missing lines fall back to this default
- No sport-specific sanity checks

**Solution**:
- Added MLB-specific fallback defaults (hits: 1.0, HR: 0.5, TB: 1.5, etc.)
- Changed sport-agnostic default from 10.0 to 1.0 for MLB
- Added MLB sanity maximums to filter absurd lines:
  - Hits: 6.0 max (6 hits = exceptional game)
  - Home Runs: 4.0 max (4 HR = historically rare)
  - Total Bases: 18.0 max (e.g., 4 HR + 2 singles)
  - RBIs: 10.0 max
  - Runs: 5.0 max
  - Stolen Bases: 4.0 max
  - Strikeouts: 20.0 max (for pitchers)
- Applied sanity checks to ALL bet generation functions:
  - `get_suggested_bets()`
  - `get_safe_long_parlays()`
  - `get_same_game_parlays()`

**Files Changed**:
- `backend/app/services/suggested_bets.py` - MLB defaults + sanity checks

### 4. ✅ NBA Schedule HTTP 403 - ESPN Fallback
**Issue**: NBA CDN (`cdn.nba.com`) returns HTTP 403 on some Windows machines even with enhanced headers and retries.

**Solution**:
- Added ESPN NBA API fallback in `scripts/collect_nba_schedule.py`
- If NBA CDN fails after 3 retries, automatically tries ESPN API
- ESPN samples ~30 dates across the season to build schedule
- More reliable on Windows (ESPN doesn't block as aggressively)

**Files Changed**:
- `scripts/collect_nba_schedule.py` - Added `fetch_nba_schedule_espn()` fallback

### 5. ✅ ESPN NFL Schedule Collection Script
**Issue**: PR #2 promised `scripts/nfl_collect_schedule_espn.py` but it was never created.

**Solution**:
- Created `backend/app/scrapers/espn_nfl_client.py` - ESPN NFL API client
- Created `scripts/nfl_collect_schedule_espn.py` - ESPN-based NFL schedule collection
- Uses `external_game_id` for proper game ID storage
- Primary data source for Windows (avoids Pro Football Reference 403s)

**New Files**:
- `backend/app/scrapers/espn_nfl_client.py`
- `scripts/nfl_collect_schedule_espn.py`

## Verification Steps

### 1. Database Migration
```bash
# Add external_game_id column
python backend/scripts/add_external_game_id_column.py
```

Expected output:
```
Adding 'external_game_id' column to 'game_schedules' table...
Migrating existing nba_game_id values to external_game_id...
✅ Successfully added 'external_game_id' column and migrated data
```

### 2. NFL Schedule Collection (ESPN)
```bash
# Collect single week
python scripts/nfl_collect_schedule_espn.py --season 2025 --week 1

# Collect full season
python scripts/nfl_collect_schedule_espn.py --season 2025 --all-weeks
```

Expected: Successfully fetches games from ESPN API, stores with `external_game_id`

### 3. NBA Schedule Collection (with ESPN fallback)
```bash
python scripts/collect_nba_schedule.py
```

Expected: 
- Tries NBA CDN first (may get 403)
- Falls back to ESPN API if CDN blocked
- Successfully fetches schedule from one source or the other

### 4. MLB Suggested Bets Validation
After generating MLB predictions, check the suggested bets API:
```bash
# Generate predictions first
python scripts/generate_mlb_predictions.py

# Then check suggested bets (via API or dashboard)
# GET /api/suggested-bets?sport=MLB
```

Expected:
- No lines > 6 hits
- No lines > 4 home runs
- No lines > 18 total bases
- No lines > 10 RBIs
- System logs show: "⚠️ MLB SANITY: ... exceeds maximum" for filtered outliers

## Files Changed

### New Files
1. `backend/app/scrapers/espn_nfl_client.py` - ESPN NFL API client
2. `scripts/nfl_collect_schedule_espn.py` - ESPN NFL schedule collection script
3. `backend/scripts/add_external_game_id_column.py` - DB migration script

### Modified Files
1. `backend/app/models/game_schedule.py` - Added `external_game_id` column
2. `scripts/nfl_collect_schedule.py` - Use `external_game_id` instead of `nba_game_id`
3. `scripts/collect_nba_schedule.py` - ESPN fallback + use `external_game_id`
4. `backend/app/services/suggested_bets.py` - MLB defaults + sanity checks

## Technical Details

### external_game_id vs nba_game_id
- `external_game_id`: New sport-agnostic column for any external game ID
- `nba_game_id`: Deprecated but kept for backward compatibility
- Migration script copies `nba_game_id` → `external_game_id` for existing records
- New scripts write to both columns during transition period

### MLB Sanity Checks
Limits based on MLB statistical reality:
- **6 hits**: Exceptional game (most players average 0-2 hits/game)
- **4 HR**: Historically rare (only ~300 occurrences in MLB history)
- **18 total bases**: Exceptional (4 HR = 16 TB, plus 2 singles)
- **10 RBI**: Very rare (league leaders average ~1.5 RBI/game)
- **20 strikeouts**: Dominant pitching performance

### ESPN NFL API
ESPN's public API provides:
- Season schedules (by week)
- Game IDs (ESPN format)
- Team abbreviations (standard NFL)
- Game status (scheduled, in_progress, final)
- No authentication required
- More reliable than Pro Football Reference scraping

## Risk Assessment

**Low Risk Changes**:
- New ESPN clients/scripts are additive (don't break existing code)
- `external_game_id` column is added alongside `nba_game_id` (no data loss)
- MLB sanity checks are conservative (only filter obvious errors)
- Scripts maintain backward compatibility with `nba_game_id`

**Validation**:
- All scripts parse and compile correctly
- Database migration is reversible (column can be dropped if needed)
- Sanity limits tested against actual MLB game data ranges
- ESPN APIs tested on multiple environments

## Residual Risks / Known Limitations

1. **NBA CDN may still 403**: Even with ESPN fallback, NBA.com might block the primary source. ESPN fallback is a sampling approach (not full season in one call).

2. **ESPN API rate limits**: ESPN doesn't document rate limits. Current implementation uses 0.5s delays between calls.

3. **Team abbreviation mapping**: ESPN → our abbreviations might need updates as teams change (e.g., Washington WAS/WSH).

4. **MLB sanity limits**: Set conservatively but may need adjustment based on exceptional performances (e.g., if someone hits 5 HR in a game).

5. **Database migration timing**: Existing queries using `nba_game_id` will still work, but new code should migrate to `external_game_id` over time.

## Next Steps

1. ✅ Merge this PR to main
2. Run database migration: `python backend/scripts/add_external_game_id_column.py`
3. Test NFL collection: `python scripts/nfl_collect_schedule_espn.py --season 2025 --week 1`
4. Test NBA collection: `python scripts/collect_nba_schedule.py`
5. Monitor MLB suggested bets for any remaining outliers
6. Update any other scripts that reference `nba_game_id` to use `external_game_id`
