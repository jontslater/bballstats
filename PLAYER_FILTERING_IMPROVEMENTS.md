# Player Filtering Improvements

## Problem
Predictions were being generated for players (like Zubac) who don't have betting lines available on DraftKings or FanDuel. This happens because:
1. Players may be injured/not playing
2. Deep bench players rarely get betting lines
3. Sportsbooks sometimes don't list players until right before the game

## Solution
Added **stricter filtering** at multiple levels to only generate predictions for players likely to have betting lines available.

---

## Filters Added

### **1. Pre-Generation Filtering (Before Processing)**
**Location**: `prediction_service.py` - `generate_predictions_for_game()`

**What it does:**
- Filters out players who are "Out" or "Doubtful" **before** trying to generate predictions
- Saves processing time by skipping injured players early

**Code:**
```python
# PRE-FILTER: For upcoming games, filter out players who are Out/Doubtful
if game.game_status in ['scheduled', 'in_progress']:
    filtered_players = []
    for player in all_players:
        injury_status = self.injury_context.get_player_injury_status(player.player_id)
        if injury_status:
            if injury_status['status'] in ['Out', 'Doubtful']:
                continue  # Skip injured players
        filtered_players.append(player)
    all_players = filtered_players
```

---

### **2. Early Generation Filter (In generate_prediction)**
**Location**: `prediction_service.py` - `generate_prediction()`

**What it does:**
- Checks injury status **before** calculating minutes/stats
- Verifies player is on the correct team
- Skips if player is Out/Doubtful

**Code:**
```python
# EARLY FILTER: For upcoming games, check if player is likely to play
if game.game_status in ['scheduled', 'in_progress']:
    # Check injury status - skip if Out or Doubtful
    injury_status = self.injury_context.get_player_injury_status(player_id)
    if injury_status:
        if injury_status['status'] in ['Out', 'Doubtful']:
            return None  # Player is out, don't generate prediction
    
    # Check if player is on the correct team for this game
    if player.current_team_id not in [game.home_team_id, game.away_team_id]:
        return None  # Player not on either team, skip
```

---

### **3. Historical Minutes Filter**
**Location**: `prediction_service.py` - `generate_prediction()`

**What it does:**
- Skips players with very low historical minutes (< 12 min/game)
- These are deep bench players who rarely get betting lines

**Code:**
```python
# FILTER: Skip players with very low historical minutes (deep bench players)
if game.game_status in ['scheduled', 'in_progress']:
    if historical_avg_minutes < 12:
        return None  # Player rarely plays, unlikely to have betting lines
```

---

### **4. Projected Minutes Filter**
**Location**: `prediction_service.py` - `generate_prediction()`

**What it does:**
- Skips players with projected minutes < 15
- Sportsbooks typically only offer lines for players expected to play 15+ minutes

**Code:**
```python
# FILTER: Skip players with very low projected minutes
# Sportsbooks typically only offer lines for players expected to play 15+ minutes
if game.game_status in ['scheduled', 'in_progress']:
    if projected_minutes < 15:
        return None  # Too few minutes, unlikely to have betting lines available
```

---

### **5. API Response Filter (Final Check)**
**Location**: `predictions.py` - `get_safe_bets()` and `get_long_shots()`

**What it does:**
- Final filter on API responses to remove predictions with very low stat means
- Catches any predictions that slipped through earlier filters

**Code:**
```python
# Additional filter: Skip predictions with very low projected stats
if pred.distribution_mean:
    min_thresholds = {
        'points': 8.0,
        'rebounds': 4.0,
        'assists': 3.0
    }
    threshold = min_thresholds.get(pred.stat_type, 5.0)
    if pred.distribution_mean < threshold:
        continue  # Too low, unlikely to have betting lines
```

---

## Filter Thresholds

### **Injury Status:**
- ❌ **Out** - Skip completely
- ❌ **Doubtful** - Skip completely
- ✅ **Questionable** - Allow (might play)
- ✅ **Probable** - Allow
- ✅ **Available** - Allow

### **Historical Minutes:**
- ❌ **< 12 minutes/game** - Skip (deep bench player)

### **Projected Minutes:**
- ❌ **< 15 minutes** - Skip (unlikely to get betting lines)

### **Distribution Mean (Final Check):**
- **Points**: ❌ < 8.0 - Skip
- **Rebounds**: ❌ < 4.0 - Skip
- **Assists**: ❌ < 3.0 - Skip

---

## Result

**Before:**
- Generated predictions for all players on both teams
- Included deep bench players, injured players, players with no betting lines

**After:**
- Only generates predictions for players likely to:
  - ✅ Be healthy and playing
  - ✅ Play 15+ minutes
  - ✅ Have betting lines available on sportsbooks

**This should eliminate predictions for players like Zubac who don't have betting lines available.**

---

## Note

The user mentioned that **"betting sites sometimes just don't list people or list them right before the game"**. This is true, so:

1. **We filter conservatively** - Only show players who are very likely to have lines
2. **Users can still generate predictions** - If a player gets a line right before the game, they can manually generate predictions
3. **The filters are reasonable** - 15+ minutes and healthy status are good indicators

If you find that some players with lines are being filtered out, we can adjust the thresholds.





