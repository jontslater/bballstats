# Historical Predictions - Why You're Not Seeing Results

## The Problem

**You're not seeing historical results because:**
- We have **463 finished games** in the database
- But we have **0 predictions** for those finished games
- The system only generates predictions for **upcoming** games (scheduled/in_progress)
- Historical results page only shows **evaluated predictions** (predictions that have been checked against actual results)

## Why This Happens

The prediction system is designed to:
1. Generate predictions **before** games are played
2. Evaluate predictions **after** games finish
3. Show results on the historical page

But if you didn't generate predictions before games finished, there's nothing to evaluate!

## Solution: Generate Historical Predictions

I've created a script to generate predictions retroactively for finished games:

```bash
# Generate predictions for last 7 days of finished games
python scripts/generate_historical_predictions.py --days 7

# Generate for specific date range
python scripts/generate_historical_predictions.py --start-date 2025-12-20 --end-date 2025-12-27

# Generate for last 30 days (more data, takes longer)
python scripts/generate_historical_predictions.py --days 30
```

## Process

### Step 1: Generate Historical Predictions
```bash
python scripts/generate_historical_predictions.py --days 7
```

This will:
- Find all finished games in the date range
- Generate predictions for those games (as if they were upcoming)
- This takes time (could be 5-15 minutes for 7 days)

### Step 2: Evaluate Predictions
After generating, evaluate them:
```bash
python scripts/evaluate_predictions.py --days 7
```

This will:
- Check actual game stats
- Compare to predictions
- Mark which bets hit/missed
- Update `actual_result`, `hit_safe`, `hit_standard`, `hit_long_shot` fields

### Step 3: View Results
Now the Historical Results page will show:
- All evaluated predictions
- Which ones hit/missed
- Accuracy statistics

## Quick Start (Recommended)

For immediate results, generate for just yesterday:

```bash
# Generate for yesterday only (fastest)
python scripts/generate_historical_predictions.py --start-date 2025-12-29 --end-date 2025-12-29

# Then evaluate
python scripts/evaluate_predictions.py --date 2025-12-29
```

## What the Historical Results Page Shows

The page filters by:
- **Only finished games** (`game_status == 'finished'`)
- **Only evaluated predictions** (`actual_result IS NOT NULL`)

So you need BOTH:
1. Predictions generated (even retroactively)
2. Predictions evaluated (checked against actual stats)

## Current Status

- ✅ 463 finished games in database
- ❌ 0 predictions for finished games
- ❌ 0 evaluated predictions

**After running the scripts:**
- ✅ Predictions generated for finished games
- ✅ Predictions evaluated
- ✅ Historical results visible

## Note

Generating predictions for many games can take time. The script processes each game and generates predictions for all players. For 7 days of games, this might take 5-15 minutes depending on how many games there were.

You can run it in the background or check progress periodically.





