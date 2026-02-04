# Historical Results Workflow

## How It Works

When you run the daily update scripts, here's what happens:

### Daily Update Process (`update_all.py` or `quick_update.py`)

1. **Collect Box Scores** (Step 1)
   - Collects box scores for yesterday's finished games
   - Stores player game stats in the database
   - This is required before predictions can be evaluated

2. **Evaluate Predictions** (Step 8 in full update, Step 2 in quick update)
   - Automatically evaluates all predictions for finished games
   - Compares predicted stats to actual stats
   - Updates predictions with `actual_result` and hit/miss status

3. **Generate New Predictions** (Step 7)
   - Generates predictions for today's upcoming games

## What You'll See

### After Running Daily Update

1. **Historical Results Page** will show:
   - All evaluated predictions from finished games
   - Hit/miss status for each prediction
   - Accuracy statistics

2. **Evaluation Status** shows:
   - Total predictions: X
   - Evaluated predictions: Y
   - Games pending: Z (games that finished but haven't been evaluated yet)

## Current Issue (12/29 Games)

The games from 12/29 don't have box scores because:
- They finished before the daily update script was run
- Box scores weren't collected for those specific games

### Solution Going Forward

✅ **This will work automatically in the future** because:

1. When you run `update_all.py` or `quick_update.py`:
   - It collects box scores for yesterday's finished games
   - It automatically evaluates predictions for those games
   - Results appear on the Historical Results page

2. The workflow is:
   ```
   Game finishes → Next day → Run update script → Box scores collected → Predictions evaluated → Results visible
   ```

## Manual Collection (If Needed)

If you need to collect box scores for past games manually:

```bash
# Collect box scores for a specific date
python scripts/collect_game_results.py --date 2025-12-29

# Or use the API endpoint
POST /api/game-results/collect-for-finished-games?days_back=7
```

Then evaluate:
```bash
# Via API
POST /api/historical-results/evaluate/all?days_back=90

# Or via script
python scripts/evaluate_all_predictions.py --days-back 90
```

## Summary

✅ **Yes, this will work in the future!**

- Daily update scripts automatically collect box scores
- Daily update scripts automatically evaluate predictions
- Historical Results page will show all evaluated predictions
- You'll see predictions for today's games after they finish and you run tomorrow's update

The 8 predictions you're seeing are from 12/26, which is the only date that had box scores collected. Once you start running the daily update scripts regularly, all future games will be automatically evaluated.





