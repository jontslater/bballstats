# Collect Game Results Script

## Where to Run

Run the script from the **project root directory** (`/Users/lisaannparr/bballstats`):

```bash
cd /Users/lisaannparr/bballstats
```

## Commands

### 1. Collect Yesterday's Games (Most Common)

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/collect_game_results.py --previous-day
```

### 2. Collect Games for a Specific Date

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/collect_game_results.py --date 2024-12-28
```

### 3. Collect Games for a Date Range

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/collect_game_results.py --start-date 2024-12-20 --end-date 2024-12-28
```

### 4. Collect All Games for a Season

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/collect_game_results.py --season 2024-25
```

## What It Does

1. **Fetches game schedules** for the specified date(s)
2. **Gets box scores** from NBA API (or Basketball Reference as fallback)
3. **Saves player stats** to the database
4. **Updates game status** to "finished"

## Fallback Behavior

- **Primary**: NBA API
- **Fallback**: Basketball Reference (if NBA API fails)

The script automatically tries Basketball Reference when NBA API doesn't return data.

## Example Output

```
🏀 Collecting Game Results...
============================================================
Collecting games for 2024-12-28...

  📊 Fetching box score for finished game 0022400123...
  ✅ Got box score from Basketball Reference!
  ✅ Created game: LAL @ GSW
  ✅ Created 20 player stats

✅ Complete!
  Games processed: 1
  Games created: 1
  Stats created: 20
```

## Troubleshooting

**If you get "ModuleNotFoundError":**
- Make sure you activated the virtual environment: `source backend/venv/bin/activate`

**If you get "No games found":**
- The date might not have any games
- Try a different date or use `--previous-day`

**If you get database errors:**
- Make sure the backend is set up and database is running
- Check `DATABASE_URL` in `.env` file


