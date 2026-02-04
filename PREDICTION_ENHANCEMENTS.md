# Prediction Enhancement Plan

## Current Factors Being Assessed

### ✅ Currently Implemented:
1. **Historical Averages** - Base distribution from past performance
2. **Minutes Projection** - With lineup confirmation, recent games weighting, injury adjustments
3. **Pace Factor** - Team pace vs league average
4. **Defense Factor** - Opponent defense vs position (points, rebounds, assists)
5. **Usage Rate** - Injury-based usage redistribution
6. **Home/Away** - Home court advantage (1.05x vs 0.97x)
7. **Rest Days** - Back-to-back (0.95x), 1 day (1.0x), 2+ days (1.02x)
8. **Travel Impact** - Basic away game factor
9. **Blowout Risk** - Based on point spread
10. **Matchup History** - Player vs team historical performance
11. **Form Trends** - Improving/declining based on recent games
12. **Injury Status** - Filtering out injured players

---

## Proposed Enhancements

### 1. **Relative Rest Advantage** ⭐ HIGH PRIORITY
**What it is:** Compare our team's rest days vs opponent's rest days
**Impact:** Teams with more rest often perform better
**Implementation:**
- Calculate rest days for both teams
- If we have 2+ days rest and opponent has 0-1 days: +2-3% boost
- If we have 0 days rest and opponent has 2+ days: -2-3% penalty
- Factor: 0.97 to 1.03

### 2. **Team Recent Performance** ⭐ HIGH PRIORITY
**What it is:** Team's win/loss record and performance in last 10 games
**Impact:** Teams on winning streaks often have better individual performances
**Implementation:**
- Calculate team's record in last 10 games
- Calculate team's average point differential in last 10 games
- If team is 7-3 or better: +1-2% boost
- If team is 3-7 or worse: -1-2% penalty
- Factor: 0.98 to 1.02

### 3. **Shooting Hot/Cold Streaks** ⭐ HIGH PRIORITY
**What it is:** Player's recent shooting percentages vs season average
**Impact:** Hot shooters tend to stay hot, cold shooters tend to stay cold
**Implementation:**
- Calculate FG%, 3P%, FT% in last 5-10 games
- Compare to season average
- If significantly above average: +2-4% boost for points
- If significantly below average: -2-4% penalty for points
- Factor: 0.96 to 1.04 (points only)

### 4. **Foul Trouble Risk** ⭐ MEDIUM PRIORITY
**What it is:** Player's historical foul rate vs opponent's ability to draw fouls
**Impact:** Players prone to fouls may see reduced minutes
**Implementation:**
- Calculate player's average fouls per game
- Calculate opponent's ability to draw fouls (opponent FTA per game)
- If high foul risk: Slight minutes reduction (0.95-0.98x)
- Factor: 0.95 to 1.0 (minutes only)

### 5. **Game Importance Context** ⭐ MEDIUM PRIORITY
**What it is:** Playoff implications, rivalry games, must-win situations
**Impact:** Players often perform better in important games
**Implementation:**
- Check if game has playoff implications (within 5 games of playoff spot)
- Check if it's a division/conference rivalry
- If important game: +1-2% boost
- Factor: 1.0 to 1.02

### 6. **Time of Day Factor** ⭐ LOW PRIORITY
**What it is:** Day games (before 6 PM) vs night games
**Impact:** Some players perform better at different times
**Implementation:**
- Check game time from schedule
- Calculate player's historical performance in day vs night games
- Apply small adjustment if significant difference
- Factor: 0.98 to 1.02

### 7. **Division/Conference Familiarity** ⭐ LOW PRIORITY
**What it is:** More games played against same division/conference teams
**Impact:** Familiarity can lead to better/worse performance
**Implementation:**
- Check if opponent is in same division (4 games/year) or conference
- Small boost for division games (more familiarity)
- Factor: 1.0 to 1.01

### 8. **Recent Pace Trends** ⭐ MEDIUM PRIORITY
**What it is:** Team's pace in last 10 games vs season average
**Impact:** Teams can change pace mid-season
**Implementation:**
- Calculate team's pace in last 10 games
- Compare to season average pace
- If significantly faster: Boost pace factor
- If significantly slower: Reduce pace factor
- Factor: Adjust existing pace factor by ±5%

### 9. **Clutch Performance** ⭐ MEDIUM PRIORITY
**What it is:** Player's performance in close games (within 5 points) vs blowouts
**Impact:** Some players perform better in competitive games
**Implementation:**
- Calculate player's stats in games decided by ≤5 points
- Compare to games decided by ≥15 points
- If better in close games: Boost for competitive matchups
- Factor: 0.98 to 1.02

### 10. **Opponent's Recent Defense** ⭐ HIGH PRIORITY
**What it is:** Opponent's defensive performance in last 10 games vs season average
**Impact:** Teams can improve/decline defensively mid-season
**Implementation:**
- Calculate opponent's points allowed in last 10 games
- Compare to season average
- If opponent is playing better defense recently: Reduce prediction
- If opponent is playing worse defense recently: Boost prediction
- Factor: 0.95 to 1.05

### 11. **Head-to-Head Player Matchups** ⭐ MEDIUM PRIORITY (Future)
**What it is:** How this specific player performs against the specific defender they'll face
**Impact:** Some players have specific matchup advantages/disadvantages
**Implementation:**
- Identify likely defensive matchup (by position)
- Check historical performance in that specific matchup
- Apply matchup-specific adjustment
- Factor: 0.90 to 1.10

### 12. **Vegas Line Analysis** ⭐ LOW PRIORITY (Future)
**What it is:** What do sportsbooks think? (if we can get betting lines)
**Impact:** Vegas lines are often very accurate
**Implementation:**
- Scrape or integrate betting line data
- Use as a validation/calibration tool
- Adjust predictions if significantly different from Vegas
- Factor: Calibration tool, not direct adjustment

---

## Implementation Priority

### Phase 1 (High Impact, Easy Implementation):
1. ✅ Relative Rest Advantage
2. ✅ Team Recent Performance  
3. ✅ Opponent's Recent Defense
4. ✅ Shooting Hot/Cold Streaks

### Phase 2 (Medium Impact):
5. ✅ Recent Pace Trends
6. ✅ Clutch Performance
7. ✅ Foul Trouble Risk
8. ✅ Game Importance Context

### Phase 3 (Lower Impact, Nice to Have):
9. Time of Day Factor
10. Division/Conference Familiarity
11. Head-to-Head Player Matchups (requires more data)
12. Vegas Line Analysis (requires external data source)

---

## Expected Impact

These enhancements should improve prediction accuracy by:
- **5-10%** better accuracy on mean predictions
- **10-15%** better identification of safe vs risky bets
- **Reduced false positives** (predictions for players who won't perform well)
- **Better long shot identification** (finding undervalued opportunities)

---

## Next Steps

1. Implement Phase 1 enhancements
2. Test against historical data
3. Measure improvement in prediction accuracy
4. Iterate based on results





