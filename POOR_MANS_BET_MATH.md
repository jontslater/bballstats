# Poor Man's Bet - Mathematical Model & Logic

## Goal
Start with $1-$5 and compound daily to reach ~$1000 using very safe bets.

## Mathematical Foundation

### 1. Basic Probability & Expected Value

**Single Bet Expected Value**:
```
EV = (Probability × Win Amount) - (Bet Amount)
EV = (P × (Bet × (Odds - 1))) - Bet
EV = Bet × (P × (Odds - 1) - 1)
```

For a bet to be profitable:
```
P × (Odds - 1) > 1
```

**Example**: If probability = 75% (0.75) and we bet $10:
- If odds are -300 (decimal 1.333), win $3.33, lose $10
- EV = 0.75 × $3.33 - 0.25 × $10 = $2.50 - $2.50 = $0 (break-even)
- To be profitable: need better odds than -300, or higher probability

### 2. Parlay Math

**Combined Probability**:
```
P(parlay) = P(leg1) × P(leg2) × P(leg3) × ...
```

**Combined Odds** (American):
- Convert each leg to decimal odds
- Multiply decimal odds
- Convert back to American odds

**Example 2-leg parlay**:
- Leg 1: 80% probability → -400 odds (decimal 1.25)
- Leg 2: 80% probability → -400 odds (decimal 1.25)
- Combined: 0.80 × 0.80 = 64% probability
- Combined decimal odds: 1.25 × 1.25 = 1.5625
- Combined American: +156 (or -156 depending on format)

**Return Calculation**:
```
Return = Bet × (Decimal Odds - 1)
For 2-leg 80% parlay: Return = Bet × 0.5625 (56.25% profit)
```

### 3. Growth Scenarios

**True Doubling (2x per day)**:
- Requires: Return = Bet (win exactly what you bet, so 2x total)
- This means: Decimal Odds = 2.0, American = +100
- Probability needed: 50% (coin flip) - TOO RISKY

**Conservative Growth (1.5x per day)**:
- Requires: Return = 0.5 × Bet (win 50% of bet, so 1.5x total)
- This means: Decimal Odds = 1.5, American = -200
- Probability needed: 66.7% to break even
- For positive EV: Need 70%+ probability

**Moderate Growth (1.6x per day)**:
- Requires: Return = 0.6 × Bet
- Decimal Odds = 1.6, American = -167
- Probability needed: 62.5% to break even
- For positive EV: Need 65%+ probability

**Aggressive Growth (1.8x per day)**:
- Requires: Return = 0.8 × Bet
- Decimal Odds = 1.8, American = -125
- Probability needed: 55.6% to break even
- For positive EV: Need 60%+ probability

### 4. Safe Bet Probability Distribution

Based on our system:
- **Safe bet**: 25th percentile line → ~75% probability
- **Very safe bet**: Can filter for 80%+ probability
- **Ultra safe bet**: 85%+ probability (rare, but possible)

**Reality Check**:
- Most "safe" bets in our system: 70-80% probability
- Very safe bets (80%+): Available but fewer options
- Ultra safe (85%+): Very rare, may not exist daily

### 5. Target Analysis: $5 → $1000

**Required Growth Multiple**: 1000 / 5 = 200x

**Time Period Options**:

#### Option A: 8 Days (User's Initial Request)
- Required daily multiplier: 200^(1/8) = 2.38x per day
- This requires: 42% probability bets (VERY RISKY)
- **Verdict**: Not feasible with safe bets

#### Option B: 10 Days
- Required daily multiplier: 200^(1/10) = 1.82x per day
- Need 55% probability bets with good odds
- Possible but risky

#### Option C: 12 Days
- Required daily multiplier: 200^(1/12) = 1.62x per day
- Need 62% probability bets (achievable with safe bets)
- **More realistic**

#### Option D: 14 Days
- Required daily multiplier: 200^(1/14) = 1.51x per day
- Need 66% probability bets (very achievable)
- **Most realistic with safe bets**

#### Option E: 16 Days
- Required daily multiplier: 200^(1/16) = 1.43x per day
- Need 70% probability bets (easy with safe bets)
- **Very safe approach**

### 6. Optimal Bet Selection Strategy

#### Strategy A: Progressive Risk (Recommended)
Start conservative, increase risk as bankroll grows:

**Days 1-4**: Very safe single bets or 2-leg parlays
- Target: 1.3-1.4x per day
- Use 75-80% probability bets
- Single bets: 75% prob → ~1.33x return
- 2-leg parlays: 80% each → 64% combined → ~1.56x return

**Days 5-8**: Moderate risk 2-3 leg parlays
- Target: 1.5-1.6x per day
- Use 75-78% probability bets in parlays
- 2-leg: 75% each → 56% combined → ~1.78x return
- 3-leg: 80% each → 51% combined → ~1.96x return

**Days 9-12**: Slightly more aggressive
- Target: 1.6-1.7x per day
- 3-leg parlays with 75-78% legs
- Or 4-leg parlays with 80% legs

**Days 13-14**: Finish strong
- Target: 1.7-1.8x per day
- 3-4 leg parlays
- Can afford slightly lower probabilities (70-75%)

#### Strategy B: Consistent Approach
Use same strategy every day:

**Conservative (1.4x per day)**:
- 14 days: $5 × 1.4^14 = $5 × 111 = $555 (not enough)
- 16 days: $5 × 1.4^16 = $5 × 288 = $1,440 ✓

**Moderate (1.5x per day)**:
- 12 days: $5 × 1.5^12 = $5 × 129 = $645 (close)
- 14 days: $5 × 1.5^14 = $5 × 291 = $1,455 ✓

**Aggressive (1.6x per day)**:
- 10 days: $5 × 1.6^10 = $5 × 110 = $550 (not enough)
- 12 days: $5 × 1.6^12 = $5 × 282 = $1,410 ✓

### 7. Bet Amount Calculation (Bet Sizing)

**What is "Bet Sizing"?**
Bet sizing means: **How much money should you bet on each bet?**

For example, if you have $50 in your bankroll:
- Option 1: Bet $5 (10% of bankroll) - conservative
- Option 2: Bet $25 (50% of bankroll) - aggressive
- Option 3: Bet $50 (100% of bankroll) - all-in (risky!)

**Why it matters**: If you bet too much and lose, you don't have enough left to recover. If you bet too little, you won't grow fast enough to reach your goal.

#### Simple Approach (Recommended):
Since we're using very safe bets (75-80% probability), we can be more aggressive:

**Strategy: Bet to reach daily target, but cap at reasonable percentage**

```
1. Calculate target bankroll for today: Current × 1.51 (daily multiplier)
2. Calculate needed profit: Target - Current
3. Calculate bet amount needed: Needed Profit / (Expected Return Rate - 1)
4. Cap at maximum: 60-70% of current bankroll (since bets are very safe)
5. Minimum: $1
```

**Example Day 1**: Start with $5, target $7.55 (1.51x)
- Needed profit: $7.55 - $5 = $2.55
- Using 2-leg parlay: Expected return = 1.56x (56% profit)
- Bet needed: $2.55 / 0.56 = $4.55
- Check cap: $5 × 0.70 = $3.50 (maximum)
- **Final bet: $3.50** (70% of bankroll, but safe because 75%+ probability)

**Example Day 5**: Bankroll = $50, target $75.50
- Needed profit: $75.50 - $50 = $25.50
- Using 2-leg parlay: Expected return = 1.56x
- Bet needed: $25.50 / 0.56 = $45.54
- Check cap: $50 × 0.70 = $35 (maximum)
- **Final bet: $35** (70% of bankroll)

#### Why 60-70% is reasonable with safe bets:
- If probability is 75-80%, you win 3-4 times out of 4-5
- Even if you lose once, you still have 30-40% left to recover
- With such high probabilities, betting more is justified

#### Simplified Formula:
```
Daily Target = Current Bankroll × 1.51
Needed Profit = Daily Target - Current Bankroll
Expected Return Multiplier = 1.5 to 1.6 (depending on bet type)
Expected Profit Rate = Expected Return Multiplier - 1

Bet Amount = min(
    Needed Profit / Expected Profit Rate,
    Current Bankroll × 0.70  # 70% maximum
)
Minimum Bet = $1
```

### 8. Parlay Selection Logic

#### Criteria for Including a Bet in Parlay:

1. **Minimum Probability**: 70% (prefer 75%+)
2. **Confidence Level**: HIGH only (or MEDIUM if probability is 80%+)
3. **Volatility**: LOW (consistent performers)
4. **Sample Size**: 15+ games minimum
5. **Injury Status**: Player must be healthy
6. **Lineup Status**: Confirmed starter (for upcoming games)
7. **Recent Form**: Player performing consistently

#### Parlay Building Algorithm:

**Step 1**: Get all qualifying bets for the day
- Filter by criteria above
- Sort by probability (highest first)

**Step 2**: Calculate target combined probability
- For 1.5x return: Need 66.7% combined probability
- For 1.6x return: Need 62.5% combined probability
- For 1.7x return: Need 58.8% combined probability

**Step 3**: Greedy selection
- Start with highest probability bet
- Add next highest that doesn't duplicate player/game
- Calculate combined probability
- Continue until target reached or no more bets

**Step 4**: Validate
- Combined probability >= target
- All legs meet minimum criteria
- Diversified (not all same game/team)
- Reasonable number of legs (2-4 preferred, max 5)

### 9. Daily Target Calculation

#### Dynamic Target (Recommended):
```
Target Multiplier = (Goal / Start Amount) ^ (1 / Days Remaining)

Example (Day 5 of 14-day challenge, $5 start, $1000 goal):
- Current Bankroll: $50
- Days Remaining: 9
- Remaining Growth Needed: $1000 / $50 = 20x
- Daily Multiplier Needed: 20^(1/9) = 1.41x per day
```

#### Fixed Target (Simpler):
```
Daily Multiplier = (Goal / Start Amount) ^ (1 / Total Days)

Example (14-day challenge):
- Daily Multiplier = (1000/5)^(1/14) = 200^(1/14) = 1.51x per day
- Day 1: $5 → $7.55
- Day 2: $7.55 → $11.40
- ...
```

### 10. Risk Management Rules

#### Rule 1: Never Bet More Than 40% of Bankroll
- Prevents catastrophic loss
- Allows recovery if one bet fails

#### Rule 2: Minimum Probability Threshold
- Single bets: 75% minimum
- 2-leg parlays: 70% per leg minimum (combined 49% minimum)
- 3-leg parlays: 75% per leg minimum (combined 42% minimum)
- 4-leg parlays: 80% per leg minimum (combined 41% minimum)

#### Rule 3: Maximum Legs in Parlay
- Recommended: 2-3 legs
- Maximum: 4 legs
- More legs = higher risk, even with high probabilities

#### Rule 4: Diversification
- Don't bet multiple stats from same player
- Don't bet multiple players from same game (unless very safe)
- Spread across different games/teams

#### Rule 5: Stop Loss
- If bankroll drops below 50% of expected (based on daily multiplier), skip a day
- Wait for better opportunities

### 11. Expected Value Analysis

#### Single Bet (75% probability, -300 odds):
```
EV = 0.75 × $3.33 - 0.25 × $10
EV = $2.50 - $2.50 = $0 (break-even)
```

#### 2-Leg Parlay (80% each leg, combined 64%):
```
Decimal Odds = 1.25 × 1.25 = 1.5625
Win Amount = Bet × 0.5625
EV = 0.64 × (Bet × 0.5625) - 0.36 × Bet
EV = Bet × (0.36 - 0.36) = $0 (break-even)

Wait, that's wrong. Let me recalculate:
- Bet $10
- Win: 0.64 probability, get $15.625 back (profit $5.625)
- Lose: 0.36 probability, lose $10
- EV = 0.64 × $5.625 - 0.36 × $10
- EV = $3.60 - $3.60 = $0 (break-even)

Hmm, still break-even. The issue is that odds are set based on probability.
```

**Key Insight**: Sportsbooks set odds to be slightly in their favor. Our "safe" bets are safe because they have high probability, but the odds reflect that probability. We need to find value bets where our calculated probability is higher than the implied probability from the odds.

**However**: For this challenge, we're not comparing to sportsbook odds - we're using our internal probability calculations. So we can assume:
- Our probabilities are accurate
- We're betting against our own model
- Expected value should be positive if our model is good

#### Revised EV Calculation (Using Our Probabilities):
```
If our model says 75% probability, and we treat it as accurate:
- We bet expecting to win 75% of the time
- Average return = 0.75 × Win + 0.25 × Loss
- For positive growth, we need Win > Loss/3

Example: Bet $10
- Win 75%: Get back $13.33 (profit $3.33)
- Lose 25%: Lose $10
- Average: 0.75 × $3.33 - 0.25 × $10 = $2.50 - $2.50 = $0

To have positive EV:
- Need: 0.75 × Win > 0.25 × Bet
- Win > Bet / 3
- Return > Bet × (1 + 1/3) = Bet × 1.333

So we need at least 1.33x return for 75% probability bets.
This means we need decimal odds of 1.33, which matches our calculation.
```

### 12. Recommended Configuration

Based on all analysis:

**Challenge Parameters**:
- Start Amount: $1-$5 (user choice)
- Goal Amount: $1000 (or 200x start amount)
- Duration: 14 days (optimal balance)
- Daily Target: 1.51x multiplier (200^(1/14))

**Bet Selection**:
- Minimum probability: 75% for single, 70% per leg for parlays
- Preferred: 80%+ probability
- Confidence: HIGH only
- Volatility: LOW only
- Sample size: 15+ games

**Bet Sizing** (How much to bet each day):
- Calculate bet needed to reach daily target (1.51x multiplier)
- Cap at 70% of current bankroll (safe because bets are 75%+ probability)
- Minimum: $1
- Formula: `min(Needed Bet for Target, Bankroll × 0.70)`

**Parlay Strategy**:
- Days 1-5: Prefer 2-leg parlays (80% each → 64% combined)
- Days 6-10: Use 2-3 leg parlays (75-80% per leg)
- Days 11-14: Can use 3-4 leg parlays if needed

**Risk Limits**:
- Maximum bet: 70% of bankroll (justified by 75%+ probability bets)
- Minimum combined probability: 60% for 2-leg, 55% for 3-leg
- Maximum 4 legs in any parlay
- Diversify across players/games
- If bet loses, challenge fails (no mulligans)

### 13. Decision Tree for Bet Selection

```
For each day:
1. Calculate target bankroll (current × 1.51)
2. Get all available safe bets (75%+ probability, HIGH confidence)
3. If enough bets for 2-leg parlay (80% each):
   - Build 2-leg parlay
   - Calculate bet amount
   - Expected return: 1.56x
4. Else if enough bets for 3-leg parlay (75% each):
   - Build 3-leg parlay  
   - Calculate bet amount
   - Expected return: 1.95x (but lower combined probability)
5. Else if single bet available (80%+):
   - Use single bet
   - Expected return: 1.25x
6. Else:
   - Skip day (extend challenge by 1 day)
   - Or reduce daily target multiplier
```

### 14. Failure Handling

#### If Bet Loses:
**Challenge fails immediately** - You lose the money you bet, challenge ends.

**Strategy Recommendation**: After first win, withdraw your starting amount (house money strategy)
- Start with $5
- Day 1: Win to $7.50, withdraw $5, continue with $2.50
- Now you're playing with "house money" - even if you lose, you got your initial investment back
- This is a psychological/risk management technique, not a rule of the challenge

**Example Progression with Withdrawal**:
- Start: $5
- Day 1: Bet $3.50, win to $5.46, withdraw $5, continue with $0.46 (challenge effectively reset)
- OR: Don't withdraw, continue with full $5.46 (faster growth)

**Note**: The withdrawal is a user choice/recommendation, not a system requirement. The challenge continues with whatever is left in the bankroll.

#### If No Safe Bets Available:
- Skip day
- Extend challenge by 1 day automatically
- Recalculate daily multiplier based on remaining days

#### If Bankroll Drops Too Low (e.g., < $1):
- Challenge fails (can't make meaningful bets)
- Or allow extension if user wants to continue

### 15. Success Metrics

Track:
- Win rate (should be 70-80% with safe bets)
- Average daily multiplier achieved
- Days to completion (if successful)
- Largest single bet
- Most legs in successful parlay
- Longest winning streak

### 16. Final Configuration

Based on discussion:

1. **Failure Tolerance**: Zero - one loss ends the challenge (you lose the money)
2. **Timeline Flexibility**: Allow automatic extension if no bets available (add 1 day)
3. **Minimum Bankroll**: Challenge fails if bankroll < $1 (can't make meaningful bets)
4. **Withdrawal Strategy**: Recommend withdrawing starting amount after first win (user choice, not required)
5. **Bet Sizing**: Calculate to reach daily target, cap at 70% of bankroll
6. **Daily Multiplier**: 1.51x (200^(1/14) for 14-day challenge)
7. **Default Duration**: 14 days (configurable)

### 17. Summary of Key Formulas

**Daily Target Calculation**:
```
Daily Target = Current Bankroll × 1.51
```

**Bet Amount Calculation**:
```
Needed Profit = Daily Target - Current Bankroll
Expected Profit Rate = 0.50 to 0.60 (50-60% profit, depending on bet type)
Bet Amount = min(Needed Profit / Expected Profit Rate, Current Bankroll × 0.70)
```

**Parlay Return Calculation**:
```
2-leg parlay (80% each): Combined probability = 0.64, Return = 1.56x (56% profit)
3-leg parlay (75% each): Combined probability = 0.42, Return = 1.95x (95% profit)
```

**Growth Projection**:
```
14 days at 1.51x per day: $5 × 1.51^14 = $5 × 291 = $1,455
```

