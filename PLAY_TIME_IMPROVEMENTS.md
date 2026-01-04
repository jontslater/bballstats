# Play Time (Minutes) Calculation Improvements

## Summary
Implemented comprehensive improvements to how the system calculates and uses assumed play time (minutes) for predictions, plus added real-time progress tracking for prediction generation.

## Backend Improvements

### 1. ✅ Use Confirmed Lineups for Minutes Calculation
**File**: `backend/app/services/prediction_service.py`

- **Change**: Now checks if a player is confirmed as a starter for the upcoming game
- **Impact**: Uses role-specific (starter vs bench) minutes baselines
- **Code**: Added `is_confirmed_starter` check before calculating historical minutes

```python
# Step 1: Check if player is confirmed starter for this game
is_confirmed_starter = self.lineup_service.is_player_starter(game_id, player_id)
```

### 2. ✅ Weight Recent Games More Heavily
**File**: `backend/app/services/distribution_engine.py`

- **Change**: Replaced simple average with exponential decay weighting
- **Impact**: Recent form matters more than older games
- **Formula**: Weight = 0.95^game_index (most recent = 1.0, older games = lower weight)

```python
# Weight recent games more heavily (exponential decay)
for i, stat in enumerate(stats_list):
    weight = 0.95 ** i  # Exponential decay
    weighted_sum += stat.minutes_played * weight
    total_weight += weight
```

### 3. ✅ Fix `is_minutes_locked` Placeholder
**File**: `backend/app/services/redistribution_engine.py`

- **Change**: Replaced always-returning-True placeholder with actual lineup analysis
- **Impact**: Properly evaluates minutes stability for variance calculations
- **Logic**: 
  - Checks if player started in 80%+ of recent games (last 30 days)
  - Requires average minutes >= 25
  - Only then considers minutes "locked"

```python
# Check if player has been a consistent starter recently
recent_starter_games = self.db.query(Lineup).join(Game).filter(...).count()
starter_rate = recent_starter_games / recent_total_games
return starter_rate >= 0.80 and avg_minutes >= 25
```

### 4. ✅ Improve Default Minutes Increase
**File**: `backend/app/services/redistribution_engine.py`

- **Change**: Replaced hardcoded +7.5 minutes with intelligent calculation
- **Impact**: Better estimates when no historical injury data exists
- **Logic**:
  - Gets injured player's average minutes
  - Same position = 60% of injured minutes (max 12 min)
  - Different position = 30% of injured minutes (max 8 min)
  - Falls back to conservative 5.0 min if no injured players found

```python
if position_match:
    minutes_increase = min(avg_min * 0.6, 12.0)
else:
    minutes_increase = min(avg_min * 0.3, 8.0)
```

### 5. ✅ Use Recent Games Parameter
**File**: `backend/app/services/prediction_service.py`

- **Change**: Now uses last 20 games instead of all-time average
- **Impact**: More responsive to recent form changes
- **Code**: Added `recent_games=20` parameter to `get_historical_avg_minutes()`

### 6. ✅ Relax Minutes Filtering Threshold
**File**: `backend/app/services/distribution_engine.py`

- **Change**: Changed from 75% to 65% of projected minutes
- **Impact**: Includes more relevant games in sample, improving accuracy
- **Code**: `min_minutes = projected_minutes * 0.65`

### 7. ✅ Add Back-to-Back Minutes Adjustment
**File**: `backend/app/services/prediction_service.py`

- **Change**: Adjusts projected minutes based on rest days
- **Impact**: Accounts for fatigue and rest
- **Logic**:
  - Back-to-back (0 rest days): -5% minutes
  - Well rested (3+ rest days): +2% minutes

```python
if rest_days == 0:  # Back-to-back
    projected_minutes *= 0.95  # -5% for fatigue
elif rest_days >= 3:  # Well rested
    projected_minutes *= 1.02  # +2% for rest
```

### 8. ✅ Add Lineup Service Method
**File**: `backend/app/services/lineup_service.py`

- **Change**: Added `is_player_starter()` method
- **Impact**: Enables checking if player is confirmed starter for specific game

```python
def is_player_starter(self, game_id: int, player_id: int) -> bool:
    """Check if a player is confirmed as a starter for a specific game."""
```

## Frontend Improvements

### 9. ✅ Real-Time Progress Tracking
**Files**: 
- `backend/app/api/predictions.py` - SSE endpoint
- `frontend/src/services/api.ts` - SSE client
- `frontend/src/pages/Dashboard.tsx` - Progress UI

- **Change**: Added Server-Sent Events (SSE) for real-time progress updates
- **Impact**: Users see progress instead of just "loading..."
- **Features**:
  - Progress bar with percentage
  - Current status message
  - Updates every 10 predictions or per game

**Backend (SSE)**:
```python
@router.post("/generate")
async def generate_predictions(request: GeneratePredictionsRequest):
    """Generate predictions with progress updates via Server-Sent Events."""
    # Uses StreamingResponse to send progress updates
```

**Frontend (Progress UI)**:
```typescript
{generationProgress && (
  <div className="bg-white rounded-lg shadow p-4">
    <div className="flex items-center justify-between mb-2">
      <span>{generationProgress.message}</span>
      <span>{generationProgress.progress}%</span>
    </div>
    <div className="w-full bg-gray-200 rounded-full h-2.5">
      <div style={{ width: `${generationProgress.progress}%` }} />
    </div>
  </div>
)}
```

## How It Works Now

1. **Check Lineup**: System checks if player is confirmed starter
2. **Get Baseline**: Uses last 20 games, weighted by recency (exponential decay)
3. **Apply Role**: If starter confirmed, uses starter-specific baseline
4. **Injury Adjustment**: Intelligently redistributes minutes based on injured players
5. **Rest Days**: Adjusts for back-to-back or well-rested scenarios
6. **Variance**: Properly evaluates minutes stability for uncertainty calculations

## Testing

To test the improvements:

1. **Confirm a lineup** for an upcoming game
2. **Generate predictions** - you should see:
   - Progress bar with real-time updates
   - More accurate minutes projections
   - Better handling of injury scenarios

3. **Check console logs** for detailed progress:
   ```
   Processing: 10/100 predictions (10%)
   Processing: 20/100 predictions (20%)
   ...
   ```

## Expected Improvements

- **More accurate minutes projections** (especially for starters vs bench)
- **Better injury handling** (smarter redistribution)
- **Recent form weighting** (recent games matter more)
- **Better user experience** (real-time progress instead of hanging)

## Notes

- The progress tracking uses Server-Sent Events (SSE) which requires keeping the connection open
- Progress updates are sent every 10 predictions or per game
- The frontend automatically handles connection errors and displays appropriate messages
- All improvements are backward compatible - existing predictions will be updated on next generation


