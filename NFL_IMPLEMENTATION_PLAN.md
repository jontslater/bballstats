# 🏈 NFL Implementation Plan - Multi-Sport Architecture

## Overview
Add NFL support to the existing app with NBA/NFL tabs. Share the same codebase with sport-specific configurations.

---

## 🎯 Architecture Design

### **Sport-Aware System**
- Add `sport` column to key tables (sport = 'NBA' or 'NFL')
- Services check sport and use appropriate logic
- Frontend has sport selector (NBA/NFL tabs)
- Same database, same codebase, sport-specific configurations

---

## 📋 Phase 1: Database Schema Updates (Week 1)

### 1.1 Add Sport Column to Core Tables
**Tables to Update:**
- ✅ `seasons` - Add `sport` column (NBA/NFL)
- ✅ `teams` - Add `sport` column
- ✅ `players` - Add `sport` column
- ✅ `games` - Add `sport` column (via season relationship)
- ✅ `player_game_stats` - Add `sport` column
- ✅ `predictions` - Add `sport` column
- ✅ `user_plays` - Add `sport` column
- ✅ `parlays` - Add `sport` column
- ✅ `poor_mans_bet_challenges` - Add `sport` column

**Migration Script:**
```python
# scripts/add_sport_column.py
# 1. Add sport column to all tables (default='NBA' for existing data)
# 2. Add indexes on (sport, ...) for performance
# 3. Add unique constraints where needed (e.g., team abbreviation + sport)
```

**Effort**: 2-3 days

### 1.2 Update PlayerGameStat Model for Multi-Sport
**Current**: Basketball-only stats (points, rebounds, assists)
**Change**: Make stats nullable, add NFL-specific columns

**Strategy**: Add nullable NFL columns, keep NBA columns
```python
# Basketball stats (existing)
points, rebounds, assists, minutes_played, ...

# NFL stats (new, nullable)
passing_yards, passing_tds, interceptions, completions, attempts
rushing_yards, rushing_tds, rushing_attempts
receptions, receiving_yards, receiving_tds, targets
snaps_played, snap_percentage
```

**Alternative**: JSON column for flexible stats (more complex but cleaner)

**Effort**: 2-3 days

### 1.3 Update Position Handling
**Current**: `position` = 'PG', 'SG', 'SF', 'PF', 'C'
**Change**: Sport-specific position validation

**NBA Positions**: PG, SG, SF, PF, C
**NFL Positions**: QB, RB, WR, TE, K, DEF (or more granular)

**Effort**: 1 day

---

## 📊 Phase 2: Sport Configuration System (Week 1-2)

### 2.1 Create Sport Config Module
**File**: `backend/app/config/sport_config.py`

```python
SPORT_CONFIGS = {
    'NBA': {
        'stat_types': ['points', 'rebounds', 'assists', 'minutes'],
        'positions': ['PG', 'SG', 'SF', 'PF', 'C'],
        'time_unit': 'minutes_played',  # vs 'snaps_played' for NFL
        'positions_by_group': {
            'guard': ['PG', 'SG'],
            'forward': ['SF', 'PF'],
            'center': ['C']
        },
        'default_stat_type': 'points'
    },
    'NFL': {
        'stat_types': [
            'passing_yards', 'passing_tds', 'interceptions',
            'rushing_yards', 'rushing_tds', 'rushing_attempts',
            'receptions', 'receiving_yards', 'receiving_tds', 'targets',
            'snaps_played', 'snap_percentage'
        ],
        'positions': ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'],
        'time_unit': 'snaps_played',
        'positions_by_group': {
            'qb': ['QB'],
            'rb': ['RB'],
            'receiver': ['WR', 'TE']
        },
        'default_stat_type': 'passing_yards'  # position-dependent
    }
}
```

**Effort**: 1 day

### 2.2 Create Sport-Aware Service Base
**File**: `backend/app/services/base_sport_service.py`

```python
class BaseSportService:
    def __init__(self, db: Session, sport: str = 'NBA'):
        self.db = db
        self.sport = sport
        self.config = SPORT_CONFIGS[sport]
    
    def get_stat_types(self):
        return self.config['stat_types']
    
    def get_positions(self):
        return self.config['positions']
    
    def get_default_stat_type(self, position: str):
        # QB -> passing_yards, RB -> rushing_yards, etc.
        ...
```

**Effort**: 2 days

---

## 🏀 Phase 3: NBA Data Migration (Week 2)

### 3.1 Mark All Existing Data as NBA
**Script**: `scripts/migrate_existing_to_nba.py`
- Set `sport = 'NBA'` on all existing records
- Verify data integrity
- Test queries with sport filter

**Effort**: 1 day

### 3.2 Update All Services to Use Sport Filter
**Services to Update:**
- `prediction_service.py` - Filter by sport
- `game_service.py` - Filter games by sport
- `player_service.py` - Filter players by sport
- All API endpoints - Accept sport parameter

**Effort**: 2-3 days

---

## 🏈 Phase 4: NFL Data Collection (Week 2-4)

### 4.1 Research NFL Data Sources
**Options:**
1. **nfl-data-py** - Python package (similar to nba_api)
2. **NFL.com scraping** - Official source
3. **Pro Football Reference** - Similar to Basketball Reference
4. **ESPN API** - May have NFL support

**Decision Needed**: Which source to use?

**Effort**: 2-3 days (research + testing)

### 4.2 Create NFL Data Collection Scripts
**Scripts to Create:**
- `scripts/nfl_collect_teams.py` - Collect NFL teams
- `scripts/nfl_collect_seasons.py` - Create NFL seasons
- `scripts/nfl_collect_schedule.py` - Collect NFL schedule
- `scripts/nfl_collect_players.py` - Collect NFL players
- `scripts/nfl_collect_game_results.py` - Collect game stats
- `scripts/nfl_collect_injuries.py` - Collect injury reports

**File Structure:**
```
backend/app/scrapers/
  ├── nba_api_client.py (existing)
  └── nfl_api_client.py (new)
```

**Effort**: 1-2 weeks

### 4.3 NFL-Specific Data Models
- Team structure (conferences/divisions)
- Player positions (QB/RB/WR/TE)
- Game structure (17 games, byes, playoffs)
- Stat collection (yards, TDs, receptions, snaps)

**Effort**: 3-4 days

---

## 🔧 Phase 5: Service Adaptations for NFL (Week 4-6)

### 5.1 Update Prediction Service
**File**: `backend/app/services/prediction_service.py`

**Changes:**
- Check `sport` parameter
- Use sport-specific stat types
- Use sport-specific position logic
- Sport-specific player filtering (snap % vs minutes)

**NFL-Specific Logic:**
- QB: Generate passing_yards, passing_tds predictions
- RB: Generate rushing_yards, rushing_tds, receptions predictions
- WR/TE: Generate receiving_yards, receiving_tds, receptions predictions

**Effort**: 1 week

### 5.2 Update Prediction Adjustments
**File**: `backend/app/services/prediction_adjustments.py`

**NBA Adjustments** (keep):
- Team position defense
- Usage rate
- Pace
- Minutes played

**NFL Adjustments** (add):
- Team defense vs position group (rush defense vs RB, pass defense vs WR)
- Touch/target share (equivalent of usage rate)
- Pace (plays per game)
- Snap percentage
- Weather impact (wind, rain)
- Game script (expected pass/run ratio)

**Effort**: 1 week

### 5.3 Update Team Defense Calculator
**File**: `backend/app/services/team_defense_calculator.py`

**NFL Defense Metrics:**
- Rush defense vs RB (yards/TDs allowed)
- Pass defense vs WR/TE (yards/TDs allowed)
- Overall team defense rankings

**Effort**: 1 week

### 5.4 Update Matchup Analyzer
**File**: `backend/app/services/matchup_analyzer.py`

**NFL Matchups:**
- RB vs Team rush defense history
- WR vs Team pass defense history
- QB vs Team defense history

**Effort**: 3-4 days

### 5.5 Update Redistribution Engine
**File**: `backend/app/services/redistribution_engine.py`

**NFL Redistribution:**
- RB1 injured → Redistribute touches to RB2/RB3
- WR1 injured → Redistribute targets to WR2/WR3
- Snap percentage redistribution

**Effort**: 3-4 days

### 5.6 Update Game Context Calculator
**File**: `backend/app/services/game_context_calculator.py`

**NFL Additions:**
- Weather conditions (wind speed, rain, snow)
- Game script prediction (expected pass/run ratio)
- Short week adjustments (Thursday games)
- Playoff implications

**Effort**: 1 week

---

## 🎨 Phase 6: Frontend Updates (Week 6-7)

### 6.1 Add Sport Selector to Layout
**File**: `frontend/src/components/Layout.tsx`

**UI:**
```
┌─────────────────────────────────────┐
│ [🏀 NBA] [🏈 NFL]  |  Dashboard | ... │
└─────────────────────────────────────┘
```

**Implementation:**
- Add sport state to Layout (or context)
- Store in localStorage
- Pass sport to all API calls

**Effort**: 1 day

### 6.2 Update API Service
**File**: `frontend/src/services/api.ts`

**Changes:**
- Add `sport` parameter to all API calls
- Default to 'NBA' if not set
- Read from context/localStorage

```typescript
// Example
getGames(date: string, sport: string = 'NBA') {
  return axios.get(`/api/games?date=${date}&sport=${sport}`);
}
```

**Effort**: 1 day

### 6.3 Update All Pages for Sport-Awareness
**Pages to Update:**
- `Dashboard.tsx` - Filter by sport
- `GamesList.tsx` - Show sport selector
- `GameDetail.tsx` - Sport-specific stat display
- `AllPredictions.tsx` - Sport-specific stat filters
- `PoorMansBet.tsx` - Sport-aware
- `BankrollRecommendations.tsx` - Sport-aware

**Stat Type Dropdowns:**
- NBA: Points, Rebounds, Assists, Minutes
- NFL: Passing Yards, Rushing Yards, Receptions, etc.

**Effort**: 3-4 days

### 6.4 Update Stat Displays
**Components to Update:**
- Prediction cards - Show appropriate stat labels
- Game details - Show appropriate stats
- Play cards - Show appropriate stats

**Effort**: 2 days

---

## 🧪 Phase 7: NFL-Specific Features (Week 7-8)

### 7.1 Advanced Bet Generator for NFL
**File**: `backend/app/services/advanced_bet_generator.py`

**NFL Combo Bets:**
- Passing + Rushing Yards (dual-threat QB)
- Receptions + Receiving Yards
- Rushing Yards + Rushing TDs
- First TD scorer
- Anytime TD scorer

**Effort**: 3-4 days

### 7.2 Weather Integration
**Service**: `backend/app/services/weather_service.py`

**Features:**
- Fetch weather for game location
- Calculate wind impact on passing
- Calculate rain/snow impact on rushing
- Adjust predictions based on weather

**API Options:**
- OpenWeatherMap
- Weather.gov
- AccuWeather

**Effort**: 3-4 days

### 7.3 Game Script Predictor
**Service**: `backend/app/services/game_script_predictor.py`

**Logic:**
- Predict expected game flow (who's favored, by how much)
- If team likely trailing → More pass attempts
- If team likely leading → More run attempts
- Adjust player props accordingly

**Effort**: 1 week

---

## ✅ Phase 8: Testing & Calibration (Week 8-9)

### 8.1 Generate NFL Predictions for Historical Games
- Collect historical NFL data (2023 season, 2024 season)
- Generate predictions retroactively
- Compare to actual results

**Effort**: 1 week

### 8.2 Calibrate NFL Probabilities
- Run prediction calibration on NFL data
- Adjust probability calculations
- Fine-tune adjustments

**Effort**: 3-4 days

### 8.3 End-to-End Testing
- Test full workflow for both sports
- Test switching between NBA/NFL
- Test data isolation (NBA data doesn't show in NFL, etc.)

**Effort**: 3-4 days

---

## 📅 Timeline Summary

| Phase | Duration | Effort |
|-------|----------|--------|
| **Phase 1: Database Schema** | Week 1 | 5-6 days |
| **Phase 2: Sport Config** | Week 1-2 | 3 days |
| **Phase 3: NBA Migration** | Week 2 | 3 days |
| **Phase 4: NFL Data Collection** | Week 2-4 | 2 weeks |
| **Phase 5: Service Adaptations** | Week 4-6 | 2 weeks |
| **Phase 6: Frontend Updates** | Week 6-7 | 1 week |
| **Phase 7: NFL-Specific Features** | Week 7-8 | 1.5 weeks |
| **Phase 8: Testing & Calibration** | Week 8-9 | 1.5 weeks |
| **TOTAL** | **8-9 weeks** | **Moderate-High** |

---

## 🎯 Quick Start (MVP Approach)

### **Minimum Viable Product (4-5 weeks)**
Focus on core functionality first:

1. **Week 1**: Database schema + sport config
2. **Week 2**: NBA migration + basic NFL data collection
3. **Week 3**: Basic NFL predictions (simple adjustments only)
4. **Week 4**: Frontend sport selector + basic NFL UI
5. **Week 5**: Testing + bug fixes

**Defer to Later:**
- Advanced game script prediction
- Weather integration (can add later)
- Advanced combo bets (can add later)

---

## 🚀 Implementation Order

### **Priority 1: Foundation**
1. ✅ Add sport column to all tables
2. ✅ Create sport config system
3. ✅ Migrate existing NBA data
4. ✅ Update services to be sport-aware

### **Priority 2: NFL Data**
5. ✅ Build NFL data collection
6. ✅ Collect NFL teams, players, games
7. ✅ Collect historical NFL stats

### **Priority 3: NFL Predictions**
8. ✅ Adapt prediction service for NFL
9. ✅ Basic NFL adjustments (team defense, snap %)
10. ✅ Generate NFL predictions

### **Priority 4: Frontend**
11. ✅ Add sport selector
12. ✅ Update all pages for sport-awareness
13. ✅ NFL-specific UI elements

### **Priority 5: Advanced Features**
14. ⏳ Weather integration
15. ⏳ Game script prediction
16. ⏳ Advanced NFL combo bets

---

## 💡 Key Design Decisions

### **Decision 1: Database Schema**
**Option A**: Add `sport` column to all tables
- ✅ Simple, clear separation
- ✅ Easy to query by sport
- ❌ Some redundancy

**Option B**: Separate databases/tables
- ✅ Complete isolation
- ❌ Code duplication
- ❌ Harder to maintain

**Recommendation**: **Option A** (sport column)

### **Decision 2: Stat Storage**
**Option A**: Separate columns for NBA/NFL stats (both nullable)
- ✅ Type-safe
- ✅ Easy queries
- ❌ More columns

**Option B**: JSON column for flexible stats
- ✅ Flexible
- ❌ Harder to query
- ❌ Less type-safe

**Recommendation**: **Option A** (separate columns)

### **Decision 3: Service Architecture**
**Option A**: Single service, check sport internally
- ✅ Code reuse
- ✅ Easier maintenance
- ❌ More conditional logic

**Option B**: Separate service classes per sport
- ✅ Clean separation
- ❌ Code duplication

**Recommendation**: **Option A** (single service with sport checks)

---

## 📝 Next Steps

1. **Review this plan** - Make sure it aligns with your vision
2. **Choose NFL data source** - Research and decide on data collection method
3. **Start Phase 1** - Begin database schema updates
4. **Set up development branch** - Create `feature/nfl-support` branch

---

## ❓ Questions to Answer

1. **NFL Data Source**: Which source should we use? (nfl-data-py, NFL.com, Pro Football Reference)
2. **Timeline**: Is 8-9 weeks acceptable, or should we prioritize MVP first?
3. **Features**: Which NFL-specific features are most important? (Weather? Game script? Advanced combos?)
4. **Testing**: Do you have access to historical NFL data for testing?

---

Let me know if you want to adjust anything or start implementing!

