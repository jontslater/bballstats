# Update Scripts

Simple scripts to keep your NBA betting analytics up to date.

## Quick Start

### Full Update (Recommended - Run Daily)
Updates everything: games, stats, analytics, injuries, predictions.

```bash
python scripts/update_all.py
```

**When to run**: Once per day, preferably in the morning after games finish.

### Quick Update (Fast - Before Games)
Just updates yesterday's games and regenerates today's predictions.

```bash
python scripts/quick_update.py
```

**When to run**: 60-120 minutes before games start (when lineups are confirmed).

## What Gets Updated

### `update_all.py` (Full Update)
1. ✅ Previous day's game results
2. ✅ Player statistics
3. ✅ Upcoming game schedules
4. ✅ Analytics (team defense, matchups, form)
5. ✅ Injury reports
6. ✅ Predictions for all upcoming games

### `quick_update.py` (Quick Update)
1. ✅ Previous day's game results
2. ✅ Predictions for today's games only

## Automation (Optional)

### Mac/Linux - Cron Job
Add to crontab (`crontab -e`):

```bash
# Daily full update at 6 AM
0 6 * * * cd /path/to/bballstats && /path/to/venv/bin/python scripts/update_all.py >> update_log.txt 2>&1
```

### Windows - Task Scheduler
Create a scheduled task to run:
```
python scripts/update_all.py
```

### Python Schedule (Background Process)
Run in background:

```bash
python scripts/scheduler.py  # (to be created)
```

## Logs

All updates are logged to:
- Console output
- `update_log.txt` file

Check logs if something goes wrong.

## Troubleshooting

**Script fails with "Module not found"**
- Make sure you're in the project root directory
- Activate your virtual environment: `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\activate` (Windows)

**No data updated**
- Check your internet connection
- Verify NBA API is accessible
- Check `update_log.txt` for errors

**Predictions not generating**
- Make sure you have at least one season of historical data
- Verify analytics have been calculated (run full update first)


