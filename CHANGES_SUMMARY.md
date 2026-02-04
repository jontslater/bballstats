# Changes Summary - User Requests

## ✅ Changes Made

### 1. Removed "Minutes" as a Betting Line
- **Changed**: Removed `minutes` from default stat types
- **Files Updated**:
  - `scripts/generate_predictions.py` - Default now: `points,rebounds,assists`
  - `backend/app/api/predictions.py` - Default now: `["points", "rebounds", "assists"]`
  - `backend/app/services/prediction_service.py` - Default now: `['points', 'rebounds', 'assists']`
- **Note**: Minutes are still used internally for calculations, just not as a betting line

### 2. Game Status Updates
- **Created**: `scripts/update_game_statuses.py` - Marks past games as 'finished'
- **Updated**: `scripts/update_all.py` - Now includes game status update step
- **Result**: Games from 12/27 and earlier are now marked as 'finished' instead of 'scheduled'
- **Run**: `python scripts/update_game_statuses.py` to update manually

### 3. Show Game Time and Team for Players
- **Backend Changes**:
  - All prediction API endpoints now return `player_team` (team abbreviation) and `game_time`
  - Updated endpoints: `/api/predictions/game/{game_id}`, `/api/predictions/safe-bets`, `/api/predictions/long-shots`, `/api/predictions/upcoming`
- **Frontend Changes**:
  - `Dashboard.tsx` - Shows team and game time for safe bets and long shots
  - `GameDetail.tsx` - Shows team for each prediction
  - `api.ts` - Updated `Prediction` interface to include `player_team` and `game_time`

### 4. Lineup Confirmation API
- **Created**: `backend/app/api/lineups.py` - New API endpoints for lineup management
- **Endpoints**:
  - `POST /api/lineups/confirm` - Confirm a starting lineup
  - `GET /api/lineups/game/{game_id}` - Get lineups for a game
  - `GET /api/lineups/game/{game_id}/team/{team_id}/confirmed` - Check if lineup is confirmed
- **Registered**: Added to `backend/app/main.py`

## 📝 Usage

### Update Game Statuses
```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate
python scripts/update_game_statuses.py
```

Or it runs automatically in `update_all.py`.

### Confirm a Lineup (API)
```bash
POST /api/lineups/confirm
{
  "game_id": 464,
  "team_id": 28,
  "starter_player_ids": [123, 456, 789, 101, 112],
  "positions": ["PG", "SG", "SF", "PF", "C"]  # Optional
}
```

### Generate Predictions (Without Minutes)
```bash
python scripts/generate_predictions.py --days 1
# Now only generates: points, rebounds, assists
```

## 🎯 What You'll See Now

1. **No more "minutes" predictions** - Only points, rebounds, assists
2. **Past games marked as finished** - Games from 12/27 show as 'finished'
3. **Team and time displayed** - Each prediction shows player's team and game time
4. **Lineup confirmation available** - Can confirm lineups via API

## 🔄 Next Steps

1. **Restart backend** to load new lineup API endpoints
2. **Refresh frontend** to see team and time info
3. **Run game status update** if needed: `python scripts/update_game_statuses.py`
4. **Regenerate predictions** without minutes: `python scripts/generate_predictions.py --days 1`





