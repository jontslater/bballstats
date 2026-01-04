# Poor Man's Bet - Final Logic Summary

## Core Concept
Start with $1-$5, compound daily using very safe bets (75-80% probability), reach ~$1000 in 14 days.

## Key Decisions (Finalized)

### 1. Challenge Parameters
- **Start Amount**: $1-$5 (user configurable)
- **Goal Amount**: $1000 (or 200x start amount)
- **Duration**: 14 days (optimal balance)
- **Daily Multiplier**: 1.51x (200^(1/14))
- **Failure Tolerance**: Zero - one loss ends challenge

### 2. Bet Selection Criteria

**Minimum Requirements**:
- Probability: 75%+ (prefer 80%+)
- Confidence Level: HIGH only
- Volatility: LOW (consistent performers)
- Sample Size: 15+ games
- Injury Status: Healthy (no Out/Doubtful/Questionable)
- Lineup: Confirmed starter (for upcoming games)

**Parlay Strategy**:
- Days 1-5: Prefer 2-leg parlays (80% each → 64% combined → 1.56x return)
- Days 6-10: Use 2-3 leg parlays (75-80% per leg)
- Days 11-14: Can use 3-4 leg parlays if needed

### 3. Bet Sizing (How Much to Bet Each Day)

**What is Bet Sizing?**
Simply: How much money should you bet? If you have $50, do you bet $5, $25, or $50?

**Our Approach**:
Since we're using very safe bets (75-80% probability), we can bet more aggressively:

```
Step 1: Calculate daily target
  Daily Target = Current Bankroll × 1.51

Step 2: Calculate needed profit
  Needed Profit = Daily Target - Current Bankroll

Step 3: Calculate bet amount
  Expected Profit Rate = 0.50 to 0.60 (50-60% profit)
  Bet Amount = Needed Profit / Expected Profit Rate

Step 4: Apply safety cap
  Maximum Bet = Current Bankroll × 0.70 (70% of bankroll)
  Final Bet = min(Bet Amount, Maximum Bet)
  Minimum Bet = $1
```

**Example**:
- Current Bankroll: $50
- Daily Target: $50 × 1.51 = $75.50
- Needed Profit: $75.50 - $50 = $25.50
- Using 2-leg parlay: Expected profit = 56% (1.56x return)
- Bet Amount: $25.50 / 0.56 = $45.54
- Safety Cap: $50 × 0.70 = $35
- **Final Bet: $35** (70% of bankroll)

**Why 70% is safe**: With 75-80% probability, you win 3-4 times out of 4-5. Even if you lose once, you still have 30% left. With such high probabilities, betting more is justified.

### 4. Failure Handling

**If Bet Loses**: Challenge fails immediately, you lose the money you bet.

**Optional Strategy** (User Recommendation):
After first win, withdraw your starting amount:
- Start with $5
- Day 1: Win to $7.50, withdraw $5, continue with $2.50
- Now playing with "house money"
- This is psychological risk management, not a system requirement

**If No Safe Bets Available**:
- Skip day, extend challenge by 1 day automatically
- Recalculate daily multiplier

**If Bankroll < $1**:
- Challenge fails (can't make meaningful bets)

### 5. Daily Workflow

```
For each day:
1. Calculate target bankroll (current × 1.51)
2. Get all available safe bets (75%+ probability, HIGH confidence)
3. Build optimal parlay (2-4 legs, depending on day)
4. Calculate bet amount to reach target (capped at 70% of bankroll)
5. Place bet
6. Wait for results
7. If win: Update bankroll, move to next day
8. If lose: Challenge fails
```

### 6. Key Formulas

**Daily Growth**:
```
Daily Target = Current Bankroll × 1.51
```

**Bet Amount**:
```
Bet = min(
    (Daily Target - Current) / Expected Profit Rate,
    Current Bankroll × 0.70
)
```

**Parlay Returns**:
```
2-leg (80% each): 64% combined probability, 1.56x return (56% profit)
3-leg (75% each): 42% combined probability, 1.95x return (95% profit)
```

**Final Growth**:
```
14 days at 1.51x: $5 × 1.51^14 = $5 × 291 = $1,455
```

### 7. Decision Logic

**Bet Selection Priority**:
1. Get all bets with 75%+ probability, HIGH confidence
2. Filter by LOW volatility, healthy players, confirmed starters
3. Sort by probability (highest first)
4. Build parlay ensuring diversification (different players/games)
5. Validate combined probability meets minimum (60% for 2-leg, 55% for 3-leg)

**Bet Amount Priority**:
1. Calculate amount needed to reach daily target
2. Apply 70% of bankroll cap
3. Ensure minimum $1 bet
4. If calculated bet > 70% cap, use the cap (will grow slower but safer)

### 8. Edge Cases

- **Not enough safe bets**: Skip day, extend challenge
- **Bet amount > bankroll**: Use 70% cap (should never happen, but safety check)
- **All games finished early**: Can't place new bet, wait for next day
- **Bankroll drops below $1**: Challenge fails
- **Game postponed**: Skip that bet, wait for next day

## Implementation Notes

This logic is now locked in and ready for implementation. The math is sound, the strategy is safe but aggressive enough to reach the goal, and the failure handling is clear (zero tolerance = one loss ends it).

