# Fixes Summary - Games, Predictions, and Parlay Builder

## Issues Fixed

### 1. ✅ Games from Yesterday Showing Instead of Today
**Problem**: Games from 12/27 were showing when user wanted to see today's games (12/28) for betting.

**Fix**: Updated `backend/app/api/games.py` to exclude finished games when filtering by today's date:
- When filtering by today's date, only shows `scheduled` and `in_progress` games
- Finished games are excluded for today (since you can't bet on finished games)
- Past dates still show all games (including finished) for historical viewing

**Code Change**:
```python
# If it's today, only show scheduled/in_progress (bettable games)
if parsed_date and parsed_date == date_type.today():
    query = query.filter(Game.game_status.in_(['scheduled', 'in_progress']))
```

### 2. ✅ Filter Predictions to Only Show Players Who Actually Played
**Problem**: Jakob Poeltl had a prediction but didn't play in the game, showing invalid betting options.

**Fix**: Updated all prediction endpoints to filter out predictions for players who didn't play:
- `get_predictions_for_game()` - Filters finished games
- `get_safe_bets()` - Filters finished games
- `get_long_shots()` - Filters finished games

**Logic**: For finished games, checks if `PlayerGameStat` exists with `minutes_played > 0`. If not, prediction is excluded.

**Code Change**:
```python
# Filter out predictions for players who didn't play (for finished games)
if game and game.game_status == 'finished':
    stat = db.query(PlayerGameStat).filter(
        PlayerGameStat.player_id == pred.player_id,
        PlayerGameStat.game_id == pred.game_id,
        PlayerGameStat.minutes_played > 0
    ).first()
    if not stat:
        continue  # Skip this prediction
```

### 3. ✅ Game Time Scraper Created
**Problem**: Game times showing as 12:00 AM because NBA API doesn't provide times.

**Fix**: Created `backend/app/scrapers/game_time_scraper.py` to scrape game times from NBA.com:
- Scrapes NBA.com schedule pages
- Parses various time formats (8:00 PM ET, 20:00, etc.)
- Handles timezone conversions
- Returns game times as ISO format strings

**Note**: This scraper needs to be integrated into the schedule collection script. The structure is ready but may need adjustment based on NBA.com's actual HTML structure.

### 4. ✅ Parlay Builder Feature
**Problem**: User wanted to create parlays (combining multiple bets).

**Fix**: Created complete parlay system:

#### Backend:
- **Model**: `backend/app/models/parlay.py`
  - Stores parlay with multiple plays
  - Calculates combined odds and probability
  - Tracks status (pending, hit, miss, partial)
  
- **API**: `backend/app/api/parlays.py`
  - `POST /api/parlays` - Create parlay
  - `GET /api/parlays` - List all parlays
  - `GET /api/parlays/{id}` - Get specific parlay
  - `PUT /api/parlays/{id}` - Update parlay
  - `DELETE /api/parlays/{id}` - Delete parlay

- **Features**:
  - Combines multiple plays into one parlay
  - Calculates total odds (multiplies probabilities)
  - Tracks which legs hit/miss
  - Supports partial wins

#### Frontend (To Be Built):
- Need to create parlay builder UI component
- Allow selecting multiple plays
- Show combined odds
- Display parlay status

## Files Modified

1. `backend/app/api/games.py` - Filter finished games for today
2. `backend/app/api/predictions.py` - Filter predictions for players who didn't play
3. `backend/app/scrapers/game_time_scraper.py` - NEW: Game time scraper
4. `backend/app/models/parlay.py` - NEW: Parlay model
5. `backend/app/models/user_play.py` - Added relationship to parlays
6. `backend/app/api/parlays.py` - NEW: Parlay API endpoints
7. `backend/app/main.py` - Registered parlay router
8. `backend/app/models/__init__.py` - Added Parlay to exports

## Next Steps

1. **Integrate Game Time Scraper**: Update `scripts/collect_schedules.py` to use the game time scraper
2. **Build Parlay Builder UI**: Create frontend component for building parlays
3. **Test Filtering**: Verify that finished games and non-playing players are properly filtered
4. **Update Database**: Run migrations to add `parlays` and `parlay_plays` tables

## Testing

To test the fixes:

1. **Today's Games**:
   ```bash
   # Should only show scheduled/in_progress games for today
   curl http://localhost:8000/api/games?game_date=2025-12-28
   ```

2. **Filtered Predictions**:
   ```bash
   # Should not show predictions for players who didn't play
   curl http://localhost:8000/api/predictions/game/{game_id}
   ```

3. **Parlay Creation**:
   ```bash
   curl -X POST http://localhost:8000/api/parlays \
     -H "Content-Type: application/json" \
     -d '{"play_ids": [1, 2, 3], "name": "My Parlay"}'
   ```

## Notes

- The game time scraper may need adjustment based on NBA.com's actual HTML structure
- Parlay odds calculation assumes independent events (multiplies probabilities)
- Frontend parlay builder UI still needs to be created
- Database migration needed for new `parlays` table


