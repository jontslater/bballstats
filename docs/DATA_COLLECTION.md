# Data Collection Guide

This guide documents the improved data collection scripts for NFL, NBA, and MLB.

## Overview of Changes

### 1. NFL Schedule & Game Results
- **Problem**: Pro Football Reference (PFR) returns HTTP 403 on Windows machines
- **Solution**: 
  - Enhanced PFR scraper with better headers and exponential backoff retries
  - Created ESPN NFL API client as primary data source
  - New script: `nfl_collect_schedule_espn.py` uses ESPN API with PFR fallback

### 2. NBA Schedule Collection
- **Problem**: NBA CDN returns HTTP 403 errors
- **Solution**:
  - Enhanced headers with full browser-like request headers
  - Added exponential backoff retry logic (4s, 8s, 16s delays)
  - Better error messages guiding users on network/VPN solutions

### 3. MLB Data Collection
- **Problem**: Position assignments defaulted all players to 'P' (Pitcher)
- **Solution**:
  - Updated `get_or_create_mlb_player()` to properly detect batter vs pitcher roles
  - Uses `is_batter` and `is_pitcher` flags from MLB Stats API
  - Correctly assigns position 'DH' for batters, 'P' for pitchers

### 4. Prediction Service MLB Awareness
- **Problem**: NBA minutes thresholds were being applied to MLB (PA/IP)
- **Solution**:
  - Added MLB-specific thresholds: 2+ PA for batters, 1+ IP for pitchers
  - Separate minimum thresholds per sport (MLB: 2.0, NFL: 5.0, NBA: 12.0)

### 5. Suggested Bets Outlier Filter
- **Problem**: Absurd lines like "HR Over 10.0" or "Hits Over 10.0" appeared
- **Solution**:
  - Added MLB-specific sanity maximums (hits: 6, HRs: 4, RBIs: 10, etc.)
  - Enhanced 5x recent maximum validation
  - Applied filters to all parlay generation functions

## Running Collection Scripts

### NFL Schedule Collection (Recommended: ESPN API)

```bash
# Collect current season using ESPN API (fastest, most reliable)
python scripts/nfl_collect_schedule_espn.py --all-weeks

# Collect specific week
python scripts/nfl_collect_schedule_espn.py --season 2024 --week 1

# Disable PFR fallback (ESPN only)
python scripts/nfl_collect_schedule_espn.py --all-weeks --no-pfr-fallback
```

### NFL Schedule Collection (Legacy: PFR Only)

```bash
# Use original PFR scraper (may get 403)
python scripts/nfl_collect_schedule.py --all-weeks

# Collect specific week
python scripts/nfl_collect_schedule.py --season 2024 --week 1
```

### NFL Game Results

```bash
# Collect yesterday's games
python scripts/nfl_collect_game_results.py --previous-day

# Collect specific date
python scripts/nfl_collect_game_results.py --date 2024-09-08

# Collect for specific season
python scripts/nfl_collect_game_results.py --season 2024 --date 2024-09-08
```

### NBA Schedule Collection

```bash
# Collect full season schedule from NBA CDN
python scripts/collect_nba_schedule.py

# Note: If you encounter HTTP 403:
# 1. Try from a different network
# 2. Use a VPN
# 3. Wait and retry (CDN may temporarily block)
```

### MLB Game Results

```bash
# Collect yesterday's games
python scripts/mlb_collect_game_results.py --previous-day

# Collect specific date
python scripts/mlb_collect_game_results.py --date 2024-07-15

# Collect season range (skip dates with existing stats)
python scripts/mlb_collect_game_results.py --season 2025 --days 90 --skip-existing

# Collect full season
python scripts/mlb_collect_game_results.py --season 2025 --start-date 2025-03-27 --end-date 2025-10-01
```

## Troubleshooting

### HTTP 403 Errors

**NFL (Pro Football Reference)**:
- Use `nfl_collect_schedule_espn.py` instead - it uses ESPN API which is more reliable
- If ESPN also fails, the script will fall back to PFR with enhanced headers
- PFR may still block - wait 24 hours or use VPN

**NBA (NBA CDN)**:
- Enhanced headers should work from most networks
- If still blocked: Try VPN or different network
- CDN blocks are usually temporary (try again in a few hours)

**MLB (MLB Stats API)**:
- MLB Stats API is public and doesn't typically block
- No rate limits - collection is fast and reliable

### Rate Limiting

All scripts include built-in rate limiting:
- NFL (PFR): 2-3 seconds between requests
- NFL (ESPN): 0.5 seconds between requests
- NBA CDN: No explicit rate limit needed
- MLB API: 0.3 seconds between requests

### Validation & Data Quality

The system now validates:
1. **Outlier lines**: MLB stats >5x recent max are filtered
2. **Sanity maximums**: MLB stats have hard ceilings (hits: 6, HRs: 4, etc.)
3. **Player positions**: Properly assigned based on batting/pitching stats
4. **Sport thresholds**: Correct PA/IP/minutes minimums per sport

## Architecture Changes

### New Files Created
- `backend/app/scrapers/espn_nfl_client.py`: ESPN NFL API client
- `scripts/nfl_collect_schedule_espn.py`: ESPN-based NFL schedule collection
- `docs/DATA_COLLECTION.md`: This documentation file

### Files Modified
- `backend/app/scrapers/pro_football_reference.py`: Enhanced headers + retry logic
- `scripts/collect_nba_schedule.py`: Enhanced headers + retry logic
- `scripts/mlb_collect_game_results.py`: Fixed position assignments
- `backend/app/services/prediction_service.py`: MLB-aware thresholds
- `backend/app/services/suggested_bets.py`: Outlier filters

## Performance Notes

### Speed Comparison (Full Season)

**NFL Schedule Collection**:
- ESPN API: ~30 seconds (22 weeks, recommended)
- PFR Scraping: ~90+ seconds (with 2s delays)

**MLB Game Results** (90 days):
- MLB Stats API: ~3-5 minutes (no rate limits, very fast)

**NBA Schedule Collection**:
- NBA CDN: ~5 seconds (single JSON fetch)

## Recommended Collection Flow

### For Regular Updates (Daily)

```bash
# 1. Collect yesterday's completed games
python scripts/nfl_collect_game_results.py --previous-day
python scripts/mlb_collect_game_results.py --previous-day

# 2. Update schedules (if needed for new weeks)
python scripts/nfl_collect_schedule_espn.py --season 2024 --week <current_week>

# 3. Generate predictions for today's games
python scripts/generate_nfl_predictions.py
python scripts/generate_mlb_predictions.py
```

### For Initial Setup (Backfill)

```bash
# 1. Seed teams and seasons (one-time)
python scripts/nfl_seed_teams.py
python scripts/seed_mlb_teams.py
python scripts/collect_nba_teams.py

# 2. Collect full season schedules
python scripts/nfl_collect_schedule_espn.py --all-weeks
python scripts/collect_nba_schedule.py

# 3. Backfill historical game results
python scripts/mlb_collect_game_results.py --season 2025 --days 180 --skip-existing
# NFL: Collect week by week as needed
```

## Support

If collection scripts fail after trying these solutions:
1. Check network connectivity
2. Verify database credentials
3. Ensure seasons are seeded (`season_id` exists)
4. Check terminal output for specific error messages
5. Review logs in `/tmp/cursor/` if running in cloud agent

For ESPN API failures, the system will automatically fall back to PFR.
For PFR failures, wait 24 hours before retrying or use VPN.
