# Poor Man's Bet Feature - Implementation Plan

## Overview
A betting challenge feature that starts with a small amount ($1-$5) and compounds it daily by making very safe bets, with the goal of doubling (or close to doubling) each day over 8 days to reach ~$1000.

**Goal**: $5 over 8 days → ~$1000 (approximately 200x, or ~2x per day)

## Core Requirements

1. **Start Amount**: $1 - $5 (configurable)
2. **Time Period**: 8 days (configurable)
3. **Target**: Double (or close to double) each day
4. **Bet Selection**: VERY safe bets (high confidence, high probability)
5. **Flexibility**: Can use single bets, 2-3 leg parlays, or more legs if confidence is high enough
6. **Tracking**: Track bankroll over time, wins/losses, progress toward goal

## Technical Design

### Database Model: `poor_mans_bet_challenge`

```sql
CREATE TABLE poor_mans_bet_challenges (
    challenge_id SERIAL PRIMARY KEY,
    name VARCHAR(200),
    start_amount DECIMAL(10, 2) NOT NULL,  -- $1-$5
    target_amount DECIMAL(10, 2) NOT NULL,  -- ~$1000 for 8 days from $5
    days_target INTEGER NOT NULL,  -- 8 days
    current_bankroll DECIMAL(10, 2) NOT NULL,  -- Current amount
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, failed
    start_date DATE NOT NULL,
    target_date DATE,  -- start_date + days_target
    current_day INTEGER DEFAULT 1,  -- Which day of the challenge
    total_bets INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);
```

### Database Model: `poor_mans_bet_day`

```sql
CREATE TABLE poor_mans_bet_days (
    day_id SERIAL PRIMARY KEY,
    challenge_id INTEGER REFERENCES poor_mans_bet_challenges(challenge_id),
    day_number INTEGER NOT NULL,  -- Day 1, 2, 3, etc.
    bet_date DATE NOT NULL,
    starting_bankroll DECIMAL(10, 2) NOT NULL,
    bet_amount DECIMAL(10, 2) NOT NULL,
    bet_type VARCHAR(20),  -- 'single', 'parlay'
    parlay_id INTEGER REFERENCES parlays(parlay_id),  -- If parlay bet
    play_id INTEGER REFERENCES user_plays(play_id),  -- If single bet
    target_return DECIMAL(10, 2),  -- Expected return if wins
    actual_return DECIMAL(10, 2),  -- Actual return after bet resolves
    ending_bankroll DECIMAL(10, 2),  -- Bankroll after this bet
    status VARCHAR(20) DEFAULT 'pending',  -- pending, hit, miss
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);
```

## Service: `PoorMansBetService`

### Core Methods

1. **`create_challenge(start_amount, days_target, name=None)`**
   - Create a new challenge
   - Calculate target amount (start_amount * 2^days or similar)
   - Initialize bankroll tracking

2. **`get_daily_bet_suggestion(challenge_id, game_date)`**
   - Find the safest bets for today
   - Calculate optimal bet amount to reach daily target
   - Suggest single bet or parlay based on confidence
   - Return bet suggestion with expected return

3. **`calculate_optimal_bet_amount(current_bankroll, target_bankroll, bet_probability)`**
   - Calculate how much to bet to reach target
   - Formula: `bet_amount = (target_bankroll - current_bankroll) / (odds - 1)`
   - For doubling: if probability is 75%, we need ~1.33x return (not quite double)
   - Account for risk tolerance (don't bet entire bankroll)

4. **`find_safest_bets(game_date, min_probability=0.75, limit=20)`**
   - Get safe bets for the day (probability >= 75%)
   - Filter by confidence level (HIGH only)
   - Sort by probability (highest first)
   - Diversify by players/games if building parlay

5. **`build_safe_parlay(bets, target_probability=0.75)`**
   - Combine safe bets into parlay
   - Ensure combined probability meets threshold
   - Limit to 2-4 legs for safety
   - Calculate combined odds/probability

6. **`record_bet(challenge_id, day_number, bet_amount, bet_type, parlay_id=None, play_id=None)`**
   - Record the bet for the day
   - Update challenge bankroll
   - Track bet status

7. **`resolve_bet(day_id, result)`**
   - Update bet status (hit/miss)
   - Update bankroll
   - Move to next day if won
   - Mark challenge as failed if lost

8. **`get_challenge_status(challenge_id)`**
   - Get current status
   - Show progress, days remaining
   - Show current bankroll vs target
   - Show bet history

## API Endpoints

### `POST /api/poor-mans-bet/challenges`
Create a new challenge
```json
{
  "start_amount": 5.00,
  "days_target": 8,
  "name": "My Poor Man's Bet Challenge"
}
```

### `GET /api/poor-mans-bet/challenges`
List all challenges (active and completed)

### `GET /api/poor-mans-bet/challenges/{challenge_id}`
Get challenge details and status

### `POST /api/poor-mans-bet/challenges/{challenge_id}/suggest-bet`
Get daily bet suggestion
```json
{
  "game_date": "2025-01-04"
}
```

### `POST /api/poor-mans-bet/challenges/{challenge_id}/place-bet`
Record a bet for the day
```json
{
  "day_number": 1,
  "bet_amount": 5.00,
  "bet_type": "parlay",
  "parlay_id": 123,
  "notes": "2-leg parlay with high confidence"
}
```

### `GET /api/poor-mans-bet/challenges/{challenge_id}/history`
Get bet history for challenge

### `PUT /api/poor-mans-bet/challenges/{challenge_id}/resolve-day/{day_id}`
Resolve a bet (update status after game)
```json
{
  "status": "hit",
  "actual_return": 10.50
}
```

## Bet Selection Strategy

### Criteria for Safe Bets:
1. **Probability**: >= 75% (preferably 80%+)
2. **Confidence Level**: HIGH only
3. **Volatility**: LOW (consistent performers)
4. **Injury Status**: Player must be healthy, no questionable status
5. **Lineup**: Player should be confirmed starter (for upcoming games)
6. **Sample Size**: At least 15+ games in historical data
7. **Recent Form**: Player performing consistently

### Parlay Strategy:
- **2-leg parlay** with 80%+ each leg = ~64% combined (might be too risky)
- **3-leg parlay** with 85%+ each leg = ~61% combined (better, but still risky)
- **Alternative**: Use lower probability bets but with better odds (e.g., 70% probability but better payout)

### Bet Amount Calculation:
For daily doubling with safe bets:
- If betting on 75% probability bet, we get ~1.33x return (not 2x)
- Need to either:
  - Accept slower growth (1.33x per day = ~8x over 8 days, not 256x)
  - Use parlays to get better odds (2-leg parlay of 75% bets = ~1.78x return)
  - Mix safer single bets with riskier parlays

**Recommended Approach**:
- Day 1-3: Single safe bets (75-80% probability) → ~1.25-1.33x return
- Day 4-6: 2-leg safe parlays (80%+ each) → ~1.6-1.78x return  
- Day 7-8: 2-3 leg parlays (75-80% each) → ~1.9-2.0x return to finish strong

This allows for slower start (safer) and faster finish (slightly riskier but still safe).

## Frontend Implementation

### Components Needed:

1. **Challenge List Page**
   - Show all challenges (active/completed)
   - Create new challenge button
   - Progress indicators

2. **Challenge Detail Page**
   - Current bankroll vs target
   - Progress bar
   - Days remaining
   - Bet history table
   - "Get Today's Bet" button
   - Suggested bet display

3. **Daily Bet Suggestion Component**
   - Show suggested bet (single or parlay)
   - Show probability and expected return
   - Show bet amount
   - "Place Bet" button
   - Bet details (players, lines, etc.)

4. **Bet History Component**
   - Table of all bets in challenge
   - Status (pending/hit/miss)
   - Amounts, returns
   - Dates

## Implementation Steps

### Phase 1: Database & Models
1. Create database models (`PoorMansBetChallenge`, `PoorMansBetDay`)
2. Create migration script
3. Add models to `backend/app/models/__init__.py`

### Phase 2: Service Layer
1. Create `PoorMansBetService` class
2. Implement bet selection logic
3. Implement bet amount calculation
4. Implement parlay building
5. Test with sample data

### Phase 3: API Endpoints
1. Create `backend/app/api/poor_mans_bet.py`
2. Implement CRUD endpoints
3. Implement bet suggestion endpoint
4. Implement bet placement/resolution endpoints
5. Add router to `main.py`

### Phase 4: Frontend
1. Create challenge list page
2. Create challenge detail page
3. Create daily bet suggestion component
4. Integrate with API
5. Add navigation/routing

### Phase 5: Testing & Refinement
1. Test with real data
2. Refine bet selection criteria
3. Test bet amount calculations
4. Validate probability thresholds
5. User testing

## Mathematical Considerations

### Doubling Strategy
- **True doubling**: Requires 2x return = -100 odds (50% probability) - too risky
- **Safe doubling**: Use 75-80% probability = 1.25-1.33x return
- **Parlay doubling**: 2-leg parlay of 80% bets = 0.64 probability, ~1.56x return
- **Compromise**: Accept ~1.5-1.7x per day average to balance safety and growth

### Example Progression (Starting with $5):
- Day 1: $5 → $7.50 (1.5x, 2-leg parlay of 75% bets)
- Day 2: $7.50 → $11.25 (1.5x)
- Day 3: $11.25 → $16.88 (1.5x)
- Day 4: $16.88 → $25.31 (1.5x)
- Day 5: $25.31 → $37.97 (1.5x)
- Day 6: $37.97 → $56.95 (1.5x)
- Day 7: $56.95 → $85.43 (1.5x)
- Day 8: $85.43 → $128.14 (1.5x)

This gives ~25x growth over 8 days (not 256x true doubling, but much safer).

To reach $1000 from $5 in 8 days, need ~200x growth = ~2.35x per day average.

### Alternative: Accept Longer Timeline
- 10 days at 1.5x per day = 57x growth = $5 → $285
- 12 days at 1.5x per day = 129x growth = $5 → $645  
- 14 days at 1.5x per day = 291x growth = $5 → $1,455 ✓

**Recommendation**: Make days_target configurable, default to 12-14 days for realistic safe growth to $1000.

## Edge Cases & Error Handling

1. **No safe bets available**: Skip day, extend challenge
2. **Bet loses**: Mark challenge as failed, allow restart
3. **Games postponed**: Skip day, adjust timeline
4. **Insufficient bankroll**: Alert user, suggest lower bet amount
5. **All games finished**: Can't place new bet, wait for next day

## Future Enhancements

1. **Multiple challenges**: Run multiple challenges simultaneously
2. **Custom strategies**: Allow user to choose aggressive vs conservative
3. **Statistics**: Track success rate, average days to completion
4. **Social features**: Share challenges, compare with others
5. **Notifications**: Alert when daily bet is ready
6. **Automated betting**: Auto-place suggested bets (optional)




