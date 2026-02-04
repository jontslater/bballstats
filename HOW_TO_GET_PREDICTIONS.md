# How to Get Predictions

## Quick Answer

**Yes, you need to restart the backend** to load the new suggested bets endpoints.

**No, it's not about time of day** - predictions need to be generated manually.

## Steps to Get Predictions

### 1. Restart Backend
The backend needs to be restarted to load the new `suggested_bets` API endpoints.

**Stop the current backend** (Ctrl+C in the terminal where it's running), then:

```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --reload
```

### 2. Generate Predictions
Predictions are **not automatically generated**. You need to create them:

**Option A: Use the Frontend Button**
1. Go to the Dashboard
2. Click "Generate Predictions" button
3. Wait for the progress bar to complete

**Option B: Use the Script**
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/generate_predictions.py --days 1
```

### 3. View Suggested Bets
Once predictions are generated:
- Suggested bets will appear automatically on the Dashboard
- Suggested parlays will appear below the suggested bets
- You'll see rankings based on probability, confidence, and quality

## Why No Predictions?

**Current Status**:
- ✅ Games exist for today (4 games)
- ❌ No predictions generated yet (0 predictions)
- ✅ Prediction system is ready to use

**The system doesn't auto-generate predictions** - you need to:
1. Click "Generate Predictions" button, OR
2. Run the prediction generation script

## After Restarting Backend

1. **Refresh your frontend** (hard refresh: Cmd+Shift+R)
2. **Click "Generate Predictions"** button
3. **Wait for completion** (watch the progress bar)
4. **Suggested bets and parlays will appear** automatically

## Troubleshooting

If predictions still don't appear after generating:
1. Check backend logs for errors
2. Verify games exist for today: `python scripts/check_collection_progress.py`
3. Check if players have enough historical data (need ≥15 games)





