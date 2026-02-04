# Daily Workflow Guide

## Two Types of Updates Needed

### 1. **Collect Yesterday's Game Results** (Get actual stats)
This needs to be done **once per day** to get the actual player stats from finished games.

### 2. **Generate Predictions** (Create betting picks)
This can be done **multiple times per day** as lineups/injuries change.

---

## Current Setup

### ❌ The Frontend Button Does NOT Collect Game Results

The "Generate Predictions" button on the frontend:
- ✅ Generates predictions for upcoming games
- ❌ Does NOT collect yesterday's game results
- ❌ Does NOT update player stats from finished games

### ✅ You Need to Run the Collection Script

To get yesterday's game results, you need to run:

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/collect_game_results.py --previous-day
```

---

## Recommended Daily Workflow

### Option 1: Manual (Current Setup)

**Morning (once per day):**
```bash
# 1. Collect yesterday's game results
python scripts/collect_game_results.py --previous-day

# 2. Then use the frontend button to generate predictions
# (Click "Generate Predictions" on the dashboard)
```

**Throughout the day:**
- Just click "Generate Predictions" button as needed
- No need to collect results again (already done in morning)

### Option 2: Automated (Recommended)

**Set up a daily cron job** to automatically collect game results:

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 6 AM)
0 6 * * * cd /Users/lisaannparr/bballstats && /Users/lisaannparr/bballstats/backend/venv/bin/python scripts/collect_game_results.py --previous-day >> /Users/lisaannparr/bballstats/collection_log.txt 2>&1
```

Then throughout the day:
- Just use the frontend "Generate Predictions" button
- Results are already collected automatically

### Option 3: Full Update Script

If you want to update everything at once:

```bash
python scripts/update_all.py
```

This does:
- ✅ Collects game results
- ✅ Updates schedules
- ✅ Recalculates analytics
- ✅ Updates injuries
- ✅ Generates predictions

---

## Summary

**To answer your question:**

- **Game Results Collection**: You need to run the script manually (or set up automation)
- **Prediction Generation**: Use the frontend button - it works great!

**Best Practice:**
1. Set up a cron job to collect results automatically each morning
2. Use the frontend button to generate predictions throughout the day

---

## Future Improvement

We could add a button to the frontend to collect game results, but for now:
- The script is the reliable way to do it
- It can be automated with cron
- The frontend button handles predictions (which is what you need most often)





