# Frontend Not Showing Data - Fix Applied

## Problem
The frontend was showing no games or predictions because:
1. **No upcoming games in database** - The prediction service looks for `Game` records, but upcoming games were only stored in `GameSchedule` records
2. **Schedule collection wasn't working** - The `update_schedules()` function wasn't properly implemented

## Fix Applied

### 1. Fixed Schedule Collection (`scripts/collect_schedules.py`)
- Added `update_upcoming_schedules()` function that can be called from `update_all.py`
- This collects upcoming game schedules from the NBA API

### 2. Created Game Records from Schedules (`scripts/create_games_from_schedules.py`)
- New script that creates `Game` records from `GameSchedule` records
- This is needed because the prediction service works with `Game` records, not `GameSchedule`
- Links schedules to games so they stay in sync

### 3. Updated Master Script (`scripts/update_all.py`)
- Now properly calls schedule collection
- Then creates Game records from schedules
- Then generates predictions

## How to Use

### Option 1: Run the Full Update Script
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/update_all.py
```

This will:
1. ✅ Collect game results (previous day)
2. ✅ Update player stats
3. ✅ **Collect upcoming schedules** (NEW - fixed!)
4. ✅ **Create Game records from schedules** (NEW!)
5. ✅ Recalculate analytics
6. ✅ Update injuries
7. ✅ Update lineups
8. ✅ **Generate predictions** (will now work!)

### Option 2: Use Frontend Button
The "Generate Predictions" button in the frontend will:
- Call the API endpoint `/api/predictions/generate`
- Which creates Game records from schedules if needed
- Then generates predictions

### Option 3: Manual Steps (if needed)
```bash
# Step 1: Collect schedules (next 7 days)
python scripts/collect_schedules.py --days 7

# Step 2: Create Game records from schedules
python scripts/create_games_from_schedules.py --days 7

# Step 3: Generate predictions
python scripts/generate_predictions.py --days 1
```

## What to Expect

After running the update script, you should see:
- ✅ Upcoming games in the database
- ✅ Predictions generated for those games
- ✅ Frontend showing games and predictions

## Troubleshooting

If you still see no data:

1. **Check if schedules were collected:**
   ```bash
   python -c "from app.database import SessionLocal; from app.models import GameSchedule; from datetime import date; db = SessionLocal(); print(f'Schedules: {db.query(GameSchedule).filter(GameSchedule.game_date >= date.today()).count()}')"
   ```

2. **Check if Game records exist:**
   ```bash
   python -c "from app.database import SessionLocal; from app.models import Game; from datetime import date; db = SessionLocal(); print(f'Games: {db.query(Game).filter(Game.game_date >= date.today()).count()}')"
   ```

3. **Check if predictions exist:**
   ```bash
   python -c "from app.database import SessionLocal; from app.models import Prediction; db = SessionLocal(); print(f'Predictions: {db.query(Prediction).count()}')"
   ```

## Next Steps

1. Run `python scripts/update_all.py` to populate upcoming games
2. Refresh the frontend
3. You should now see games and predictions!


