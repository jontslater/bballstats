# 🏈 NFL Data Collection - Testing Guide

## ✅ Scripts Ready for Testing

### 1. ✅ NFL Teams (Already Run)
```bash
python scripts/nfl_seed_teams.py
```
**Status**: ✅ 32 teams seeded

### 2. ✅ NFL Seasons (Already Run)
```bash
python scripts/nfl_seed_seasons.py
```
**Status**: ✅ 2 seasons seeded (2023, 2024)

### 3. 🧪 NFL Schedule Collection
```bash
# Collect single week
python scripts/nfl_collect_schedule.py --season 2024 --week 1

# Collect all weeks for season
python scripts/nfl_collect_schedule.py --season 2024 --all-weeks
```

### 4. 🧪 NFL Game Results Collection
```bash
# Collect games for specific date
python scripts/nfl_collect_game_results.py --date 2024-12-22

# Collect yesterday's games
python scripts/nfl_collect_game_results.py --previous-day
```

## 🧪 Recommended Testing Steps

### Step 1: Test Schedule Collection (Single Week)
```bash
cd backend
source venv/bin/activate
cd ..
python scripts/nfl_collect_schedule.py --season 2024 --week 1
```

**Expected Result:**
- Should collect Week 1 games for 2024 season
- Creates GameSchedule records with NFL teams
- Check database for new schedule entries

### Step 2: Test Game Results (Recent Game)
```bash
# Use a date from Week 1 of 2024 (or recent game)
python scripts/nfl_collect_game_results.py --date 2024-09-05
```

**Expected Result:**
- Creates Game records
- Creates PlayerGameStat records with NFL stats:
  - Passing: yards, TDs, completions, attempts, interceptions
  - Rushing: yards, TDs, attempts
  - Receiving: receptions, yards, TDs, targets
  - Fumbles

### Step 3: Verify Data Quality

```bash
cd backend
source venv/bin/activate
python -c "
from app.database import SessionLocal
from app.models import Game, PlayerGameStat, Player, Team
from sqlalchemy import func

db = SessionLocal()
try:
    # Check NFL games
    nfl_games = db.query(Game).filter(Game.sport == 'NFL').count()
    print(f'✅ NFL Games: {nfl_games}')
    
    # Check NFL players
    nfl_players = db.query(Player).filter(Player.sport == 'NFL').count()
    print(f'✅ NFL Players: {nfl_players}')
    
    # Check NFL stats
    nfl_stats = db.query(PlayerGameStat).filter(PlayerGameStat.sport == 'NFL').count()
    print(f'✅ NFL Player Stats: {nfl_stats}')
    
    # Sample stats
    if nfl_stats > 0:
        sample_stat = db.query(PlayerGameStat).filter(PlayerGameStat.sport == 'NFL').first()
        player = db.query(Player).filter(Player.player_id == sample_stat.player_id).first()
        print(f'')
        print(f'Sample Player: {player.name}')
        print(f'  Passing Yards: {sample_stat.passing_yards}')
        print(f'  Rushing Yards: {sample_stat.rushing_yards}')
        print(f'  Receptions: {sample_stat.receptions}')
finally:
    db.close()
"
```

## 🔍 Data Accuracy Checks

After collecting data, verify:

1. **Team Names/Abbreviations**
   - ✅ All 32 NFL teams present
   - ✅ Abbreviations match standard (GB, KC, SF, etc.)

2. **Game Scores**
   - ✅ Compare to actual game results
   - ✅ Check home/away teams are correct

3. **Player Stats**
   - ✅ Compare QB passing stats to actual game
   - ✅ Compare RB rushing stats
   - ✅ Compare WR receiving stats
   - ✅ Check totals match actual game stats

4. **Player Names**
   - ✅ Names are spelled correctly
   - ✅ All key players present
   - ✅ Positions are correct (QB, RB, WR, TE)

## ⚠️ Known Limitations

1. **Snap Counts**: Pro Football Reference box scores don't include snap counts
   - Would need separate source for snap percentage data

2. **Player IDs**: No official player IDs from PFR
   - Players are identified by name + team
   - May have duplicates if player names are similar

3. **Rate Limiting**: PFR has rate limits
   - Scripts use 2-3 second delays between requests
   - May need to slow down if getting blocked

## 🐛 Troubleshooting

### Issue: No games found
- Check if date is correct (NFL games are Thu/Sun/Mon)
- Verify season exists in database
- Check PFR website directly for that date

### Issue: Team abbreviations don't match
- PFR uses some different abbreviations (GNB vs GB)
- Script should handle mapping automatically

### Issue: Missing player stats
- Box score might not be available yet
- Try again later for recent games
- Check PFR website directly

### Issue: Rate limiting errors
- Increase delay in scraper (currently 2.0 seconds)
- Wait 10-15 minutes and try again
- Process smaller date ranges

---

**Ready to test!** Start with a single week schedule, then a single game's results.

