# NBA Sports Betting Analytics Platform - Complete Project Outline

## Project Overview
A comprehensive database and UI system designed specifically for NBA sports betting. The platform analyzes player performance, team matchups, and injury impacts to provide data-driven betting recommendations with likelihood scores. Users can view all available games for a given day and see recommended picks (both high-probability "safe" bets and high-upside "long shot" opportunities) with predicted stat ranges and confidence metrics.

**Primary Use Case**: Sports betting prop bets and player performance predictions

**Data Scope**: Current season + previous season only (for accuracy and relevance)

**Deployment**: Local development environment (personal use only)

**Workflow**: Create plays from recommendations → Save plays → Track outcomes manually → Review performance

---

## Core Features

### 1. Game Schedule & Daily View
**Purpose**: Display all available games for betting on any given day

**Features**:
- Daily game schedule with matchups
- Game times and venues (home/away)
- Quick access to all picks for each game
- Filter by date, teams, or game time
- Game context (back-to-back, rest days, travel)

**UI Display**:
- Calendar view for selecting dates
- List view of games with team logos
- Expandable game cards showing all available picks

---

### 2. Player Statistics Database
**Purpose**: Central repository for NBA player data (current + previous season)

**Data Points to Capture**:
- Basic player information (name, position, team, height, weight, age)
- Current season statistics (game-by-game)
- Previous season statistics (game-by-game and season totals)
- Position classifications (PG, SG, SF, PF, C)
- Team affiliations (current and previous season)
- Recent form (last 5, 10, 15 games)

**Key Metrics** (for betting predictions):
- **Points** (per game, season average, recent average)
- **Rebounds** (total, offensive, defensive)
- **Assists**
- **Minutes Played** (critical for prop bets)
- **Steals & Blocks**
- Field goal percentage, 3-point percentage, free throw percentage
- Usage rate
- Plus/minus

**Data Structure**:
- Game-by-game granularity (not just averages)
- Home vs. away splits
- Performance trends (improving/declining)

---

### 3. Team vs. Position Performance Analytics
**Purpose**: Analyze how teams historically allow players of specific positions to perform

**Features**:
- **Points allowed by position** (current + previous season)
- **Rebounds allowed by position**
- **Assists allowed by position**
- **Minutes typically played by position** (pace of game impact)
- Matchup difficulty ratings (easy, medium, hard)
- Home vs. away defensive splits
- Recent form (last 5, 10, 20 games) - how team has been defending recently
- Pace of play metrics (fast/slow teams affect minutes and opportunities)

**Output for Betting**:
- Expected performance ranges for players based on opponent
- Matchup advantage/disadvantage indicators
- Defensive ranking by position (1-30, where 1 = worst defense = best for offense)
- Pace impact on stat totals

**Calculation Method**:
- Aggregate all games where team X played against position Y
- Calculate average points/rebounds/assists allowed to that position
- Weight recent games more heavily
- Account for home/away splits

---

### 4. Injury Tracking & Impact Analysis
**Purpose**: Monitor injuries and predict their impact on player availability and alternative player opportunities

**Data Points**:
- **Current injury status** (Out, Doubtful, Questionable, Probable, Available)
- Injury type and severity
- Date of injury and expected return
- Games missed due to injury
- Performance impact post-injury (if applicable)
- Official injury reports (from NBA, team sources)

**Impact Analysis for Betting**:
- **Identify backup/alternative players** who benefit from injuries
- **Historical playing time increases** for backups when starters are injured
  - Example: If starting PG is out, backup PG typically gets +X minutes
  - Track this pattern across all teams and positions
- **Performance patterns** of backups in starter roles
  - How do backups perform when given starter minutes?
- **Injury probability scoring** (risk of player being limited or out)
- **Minutes redistribution** - when player X is out, who gets more minutes?

**Critical for Long Shots**:
- Injuries create opportunities for backups to exceed their typical stat lines
- Track which players historically capitalize on these opportunities

---

### 4.5. Minutes & Usage Redistribution Engine
**Purpose**: When starters are injured, accurately predict how minutes and usage redistribute to backups

**Core Functionality**:
- **Historical Pattern Learning**: Analyze past games where specific players were out
  - Track which backups got more minutes
  - Track how much usage was redistributed
  - Calculate average increases per position/role
  
- **Redistribution Rules**:
  - **Minutes Redistribution**:
    - When starter is out, backup at same position typically gets +5-10 minutes
    - Other players may get +2-5 minutes (usage spread)
    - Track historical patterns per team/position
  
  - **Usage Redistribution**:
    - Typically 60-70% of injured player's usage goes to primary backup
    - Remaining 30-40% spreads to other players
    - Calculate based on historical patterns
  
- **Confidence Scoring**:
  - High confidence: 5+ historical instances of this injury pattern
  - Medium confidence: 2-4 instances
  - Low confidence: 1 instance or no history

**Implementation**:
```python
# When starter is injured
injured_player = get_injured_starter()
backup = find_backup_at_position(team, injured_player.position)

# Get historical pattern
pattern = get_injury_impact_history(injured_player, backup)

# Project new minutes
backup_projected_minutes = backup.avg_minutes + pattern.avg_minutes_increase

# Project new usage
injured_usage = injured_player.usage_rate
usage_redistribution = injured_usage * 0.65  # 65% to backup
backup_projected_usage = backup.usage_rate + usage_redistribution

# Recalculate backup's distribution with new minutes/usage
backup_distribution = recalculate_distribution(
    backup, 
    minutes=backup_projected_minutes,
    usage=backup_projected_usage
)
```

**This is what makes long shots viable** - identifying backups who get significant minutes/usage bumps.

---

### 5. Player vs. Team Matchup Analysis
**Purpose**: Individual player performance against specific teams (head-to-head history)

**Features**:
- **Head-to-head statistics** (Player X vs. Team Y)
  - How many times has this player faced this team?
  - What are their averages in those games?
- Career averages against specific teams (current + previous season only)
- Recent performance trends against teams (last 3-5 matchups)
- Home/away splits against teams
- Performance in different contexts
  - Close games vs. blowouts
  - High-scoring games vs. low-scoring games

**Usage**:
- If player has strong history vs. team → higher confidence
- If player struggles vs. team → lower confidence or avoid
- Small sample size warnings (if <3 games against team)

---

### 6. Predictive Modeling & Betting Recommendations

#### 6.1 Prediction Engine
**Purpose**: Generate stat range predictions with likelihood scores

**Input Factors**:
1. Player's season average
2. Player's recent form (last 5-10 games)
3. Opponent's defensive ranking vs. player's position
4. Head-to-head history (if available)
5. Home/away context
6. Injury status (player and teammates)
7. Pace of game (fast teams = more opportunities)
8. Game script factors (blowout risk = fewer minutes)

**Output for Each Player in Each Game**:
- **Points Range**: e.g., "18-24 points" (likely range)
- **Rebounds Range**: e.g., "6-9 rebounds"
- **Assists Range**: e.g., "4-7 assists"
- **Minutes Range**: e.g., "28-32 minutes"
- **Likelihood Score**: Percentage chance of hitting the range (e.g., 75%)

**Calculation Approach**:
- Start with player's baseline (season average, recent form)
- Adjust for opponent strength (defensive ranking)
- Adjust for matchup history (if available)
- Adjust for injury context (own injuries, teammate injuries)
- Adjust for game context (pace, home/away)
- Generate confidence interval (likely range)
- Calculate likelihood percentage

---

#### 6.2 "Safe" Bets (High Likelihood Picks)
**Purpose**: Identify high-probability outcomes for conservative betting

**Criteria**:
- **Consistent performers** (low variance in stats)
- **Favorable matchups** (weak defensive teams)
- **Strong historical data** (multiple games, consistent performance)
- **Low injury risk** (player healthy, no teammate injuries affecting minutes)
- **High floor** (rarely underperforms significantly)
- **Likelihood threshold**: 70%+ chance of hitting predicted range

**Display Format**:
- Player name, team, opponent
- Stat category (Points, Rebounds, Assists, Minutes)
- Predicted range (e.g., "22-26 points")
- Likelihood score (e.g., "78%")
- Key factors supporting the pick
- Risk factors to monitor

**Example Safe Bet**:
```
Player: LeBron James
Team: Lakers vs. Rockets
Stat: Points
Range: 24-28 points
Likelihood: 82%
Reasoning: 
  - Season avg: 25.3 ppg
  - Rockets rank 28th in points allowed to SF
  - LeBron averages 26.1 ppg vs. Rockets (last 5 games)
  - No injury concerns
```

---

#### 6.3 Long Shot Bets (High Upside Opportunities)
**Purpose**: Identify high-upside, lower-probability opportunities for bigger payouts

**Criteria**:
- **High ceiling players** (can significantly exceed averages)
- **Favorable matchups** for breakout games
- **Injury-related opportunities** (backups getting extended minutes)
- **Recent form improvements** (trending upward)
- **Minutes increase opportunities** (due to injuries, rest, or matchup)
- **Favorable game scripts** (high pace, close game expected)
- **Likelihood threshold**: 30-60% chance, but high upside if it hits

**Display Format**:
- Player name, team, opponent
- Stat category
- Predicted range (e.g., "18-25 points" - wider range, higher ceiling)
- Likelihood score (e.g., "45%")
- Upside potential (e.g., "Could hit 28+ if game script favors")
- Key opportunity factors
- Risk factors

**Example Long Shot**:
```
Player: Jordan Poole
Team: Wizards vs. Spurs
Stat: Points
Range: 18-25 points (upside: 28+)
Likelihood: 48%
Reasoning:
  - Season avg: 16.2 ppg
  - Spurs rank 25th in points allowed to SG
  - Starting SG (Kuzma) questionable - if out, Poole gets +8-10 minutes
  - Recent form: 20+ points in 3 of last 5 games
  - High pace game expected (both teams top 10 in pace)
Risk: If Kuzma plays, minutes limited, lower ceiling
```

---

### 7. Play Creation & Tracking System
**Purpose**: Allow users to create betting plays from recommendations and track their outcomes

**Features**:
- **Create Play**: Select a recommendation and create a custom play
  - Choose stat type (Points, Rebounds, Assists, Minutes)
  - Set your bet line (e.g., "Over 24.5 points")
  - Add notes/context
  - Save play with game date
  
- **Play Management**:
  - View all saved plays
  - Filter by date, status (pending, hit, miss)
  - Edit plays (before game starts)
  - Delete plays
  
- **Outcome Tracking**:
  - Mark plays as "Hit" or "Miss" after game
  - View actual result vs. predicted range
  - Track win/loss record
  - View performance statistics (win rate, ROI if tracking bet amounts)

**Database Tables**:
- **user_plays**: Stores created plays
  - play_id, player_id, game_id, stat_type, bet_line, predicted_range, likelihood, notes, created_at, outcome (hit/miss/pending), actual_result

**UI Components**:
- "Create Play" button on each recommendation
- "My Plays" page showing all saved plays
- Quick mark as hit/miss buttons
- Performance dashboard (win rate, recent plays)

---

### 8. Betting Recommendation Interface
**Purpose**: Display picks organized by game with clear likelihood indicators

**Main View - Daily Games**:
```
Today's Games - [Date]

[Game 1: Lakers @ Rockets - 8:00 PM ET]
  Safe Picks (3):
    - LeBron James: 24-28 points (82% likelihood)
    - Anthony Davis: 10-13 rebounds (75% likelihood)
    - LeBron James: 32-36 minutes (88% likelihood)
  
  Long Shots (2):
    - Rui Hachimura: 14-20 points (52% likelihood) [if AD limited]
    - Austin Reaves: 6-9 assists (45% likelihood)

[Game 2: Warriors @ Celtics - 7:30 PM ET]
  Safe Picks (2):
    ...
  Long Shots (3):
    ...
```

**Filtering Options**:
- By game
- By stat category (Points, Rebounds, Assists, Minutes)
- By likelihood threshold (e.g., show only 75%+ safe bets)
- By player name
- By team
- By position

**Sorting Options**:
- By likelihood (highest to lowest)
- By upside potential (for long shots)
- By stat category
- By game time

**Detail View** (clicking on a pick):
- Full player profile
- Detailed reasoning breakdown
- Historical performance vs. opponent
- Injury context
- Recent form chart
- Similar past matchups

---

## Technical Architecture

### Recommended Tech Stack

#### Backend: **Python with FastAPI**
- **Why**: Excellent for data analysis, web scraping, and API development
- **Libraries**: 
  - FastAPI (modern, fast web framework)
  - Pandas (data manipulation)
  - SQLAlchemy (ORM for database)
  - BeautifulSoup/Scrapy (web scraping)
  - Requests (HTTP requests)
  - NumPy (numerical computations)

#### Database: **PostgreSQL**
- **Why**: Robust relational database, excellent for complex queries, handles time-series data well
- **Features**: 
  - ACID compliance
  - Strong indexing capabilities
  - JSON support for flexible data
  - Excellent performance for analytics queries

#### Frontend: **React with TypeScript**
- **Why**: Modern, component-based, great for interactive UIs
- **Additional Libraries**:
  - React Router (navigation)
  - Axios (API calls)
  - Chart.js or Recharts (data visualization)
  - Tailwind CSS (styling)

#### Data Scraping: **Python (Scrapy or BeautifulSoup)**
- **Sources to Scrape**:
  - Basketball Reference (historical stats)
  - NBA.com (official stats, injury reports)
  - ESPN (injury reports, game data)
  - Team websites (injury reports)

#### Local Development Setup:
- **Backend**: Run FastAPI locally (development server)
- **Database**: PostgreSQL installed locally (or Docker container)
- **Frontend**: Run React locally (development server)
- **Access**: `http://localhost:3000` (frontend), `http://localhost:8000` (API)

#### Data Pipeline (Local):
- **Scheduler**: Python `schedule` library or cron jobs (for daily updates)
- **Caching**: Optional - can use in-memory caching or skip for simplicity
- **Task Queue**: Optional - can run scraping scripts manually or via scheduled tasks

**Note**: For personal use, simpler is better. Can start without complex task queues and add if needed.

---

### Database Schema (Detailed)

#### Core Tables:

**1. players**
```sql
- player_id (PK, serial)
- name (varchar)
- position (varchar) - PG, SG, SF, PF, C
- height (integer) - inches
- weight (integer) - pounds
- birth_date (date)
- current_team_id (FK -> teams)
- created_at (timestamp)
- updated_at (timestamp)
```

**2. teams**
```sql
- team_id (PK, serial)
- name (varchar) - "Los Angeles Lakers"
- abbreviation (varchar) - "LAL"
- conference (varchar) - "West" or "East"
- division (varchar)
- created_at (timestamp)
```

**3. seasons**
```sql
- season_id (PK, serial)
- season_year (varchar) - "2023-24"
- start_date (date)
- end_date (date)
- is_current (boolean)
```

**4. games**
```sql
- game_id (PK, serial)
- game_date (date)
- season_id (FK -> seasons)
- home_team_id (FK -> teams)
- away_team_id (FK -> teams)
- home_score (integer)
- away_score (integer)
- game_status (varchar) - "scheduled", "in_progress", "finished"
- pace (float) - possessions per game
- created_at (timestamp)
```

**5. player_game_stats**
```sql
- stat_id (PK, serial)
- player_id (FK -> players)
- game_id (FK -> games)
- team_id (FK -> teams) - team player was on for this game
- opponent_team_id (FK -> teams)
- minutes_played (integer) - total minutes
- points (integer)
- rebounds (integer)
- offensive_rebounds (integer)
- defensive_rebounds (integer)
- assists (integer)
- steals (integer)
- blocks (integer)
- turnovers (integer)
- personal_fouls (integer)
- field_goals_made (integer)
- field_goals_attempted (integer)
- three_pointers_made (integer)
- three_pointers_attempted (integer)
- free_throws_made (integer)
- free_throws_attempted (integer)
- plus_minus (integer)
- usage_rate (float)
- is_home (boolean)
- created_at (timestamp)
- UNIQUE(player_id, game_id)
```

**6. injuries**
```sql
- injury_id (PK, serial)
- player_id (FK -> players)
- injury_date (date)
- injury_type (varchar) - "ankle", "knee", etc.
- status (varchar) - "Out", "Doubtful", "Questionable", "Probable", "Available"
- severity (varchar) - "minor", "moderate", "severe"
- expected_return_date (date)
- actual_return_date (date)
- description (text)
- source (varchar) - where we got the info
- created_at (timestamp)
- updated_at (timestamp)
```

**7. team_position_defense** (Aggregated/Analyzed Data)
```sql
- id (PK, serial)
- team_id (FK -> teams)
- position (varchar) - PG, SG, SF, PF, C
- season_id (FK -> seasons)
- games_analyzed (integer)
- avg_points_allowed (float)
- avg_rebounds_allowed (float)
- avg_assists_allowed (float)
- avg_minutes_allowed (float)
- defensive_ranking (integer) - 1-30, 1 = worst defense
- home_avg_points_allowed (float)
- away_avg_points_allowed (float)
- last_5_games_avg_points_allowed (float)
- last_10_games_avg_points_allowed (float)
- pace (float) - team's average pace
- updated_at (timestamp)
- UNIQUE(team_id, position, season_id)
```

**8. player_team_matchups** (Head-to-Head History)
```sql
- id (PK, serial)
- player_id (FK -> players)
- opponent_team_id (FK -> teams)
- season_id (FK -> seasons)
- games_played (integer)
- avg_points (float)
- avg_rebounds (float)
- avg_assists (float)
- avg_minutes (float)
- last_5_games_avg_points (float)
- best_game_points (integer)
- worst_game_points (integer)
- updated_at (timestamp)
- UNIQUE(player_id, opponent_team_id, season_id)
```

**9. injury_impact_history** (Learning from Past Injuries)
```sql
- id (PK, serial)
- injured_player_id (FK -> players)
- beneficiary_player_id (FK -> players) - who got more minutes
- game_id (FK -> games)
- minutes_increase (integer) - how many more minutes beneficiary got
- stat_increase_points (float)
- stat_increase_rebounds (float)
- stat_increase_assists (float)
- position (varchar)
- created_at (timestamp)
```

**10. predictions** (Store Distribution-Based Predictions)
```sql
- prediction_id (PK, serial)
- player_id (FK -> players)
- game_id (FK -> games)
- stat_type (varchar) - "points", "rebounds", "assists", "minutes"
- distribution_mean (float) - adjusted mean (μ)
- distribution_std_dev (float) - adjusted standard deviation (σ)
- percentile_10 (float)
- percentile_20 (float)
- percentile_25 (float) - Safe bet line
- percentile_50 (float) - Median/Standard bet line
- percentile_75 (float)
- percentile_80 (float)
- percentile_85 (float) - Long shot line
- percentile_90 (float)
- sample_size (integer) - number of historical games used
- safe_line (float) - recommended safe bet line
- safe_probability (float) - probability of hitting safe line
- standard_line (float) - standard bet line
- standard_probability (float)
- long_shot_line (float) - long shot bet line
- long_shot_probability (float)
- bet_type (varchar) - "safe", "standard", "long_shot", "pass"
- pass_reason (text) - if bet_type is "pass", why
- confidence_level (varchar) - "HIGH", "MEDIUM", "LOW"
- volatility_level (varchar) - "LOW", "MEDIUM", "HIGH"
- reasoning (text) - key factors
- created_at (timestamp)
- updated_at (timestamp) - updated when lineups confirmed
- actual_result (integer) - filled in after game
- hit_safe (boolean) - did safe bet hit?
- hit_standard (boolean) - did standard bet hit?
- hit_long_shot (boolean) - did long shot hit?
```

**11. game_schedules** (Upcoming Games)
```sql
- schedule_id (PK, serial)
- game_date (date)
- home_team_id (FK -> teams)
- away_team_id (FK -> teams)
- game_time (timestamp)
- season_id (FK -> seasons)
- status (varchar) - "scheduled", "postponed", "cancelled"
- created_at (timestamp)
```

**12. user_plays** (User-Created Betting Plays)
```sql
- play_id (PK, serial)
- player_id (FK -> players)
- game_id (FK -> games)
- stat_type (varchar) - "points", "rebounds", "assists", "minutes"
- bet_line (varchar) - e.g., "Over 24.5", "Under 10.5"
- predicted_min (integer) - from prediction
- predicted_max (integer) - from prediction
- likelihood_score (float) - from prediction
- notes (text) - user notes
- status (varchar) - "pending", "hit", "miss"
- actual_result (integer) - filled in after game
- created_at (timestamp)
- updated_at (timestamp)
```

---

## Data Collection & Scraping Strategy

### Recommended Data Sources (Researched & Ranked):

#### 1. Basketball Reference (basketball-reference.com) - **PRIMARY SOURCE**
**Why**: Most comprehensive historical data, well-structured, widely used
**What to Scrape**:
- Player game logs (current + previous season) - game-by-game stats
- Team game logs
- Player season totals and averages
- Team defensive statistics by position
- Schedule information
- Advanced metrics (usage rate, pace, etc.)

**Frequency**: 
- Initial: Scrape previous season once
- Daily: Scrape current season game results (previous day's games)

**Challenges**:
- Rate limiting (respectful delays: 2-3 seconds between requests)
- HTML structure is generally stable but can change
- May need to handle missing data for recent games
- **Solution**: Use `nba_api` Python package (unofficial wrapper) or direct scraping with BeautifulSoup

**Reliability**: ⭐⭐⭐⭐⭐ (Excellent - industry standard)

---

#### 2. NBA.com Official Stats - **SECONDARY SOURCE**
**Why**: Official source, most up-to-date, reliable
**What to Scrape**:
- Official game statistics (verify Basketball Reference data)
- Player profiles and rosters
- Real-time injury reports (official NBA injury list)
- Game schedules

**Frequency**: 
- Daily: Verify game results
- Multiple times on game days: Check injury updates

**Challenges**:
- May have anti-scraping measures
- API endpoints may change
- **Solution**: Check for unofficial `nba_api` Python package support, or use Selenium if needed

**Reliability**: ⭐⭐⭐⭐⭐ (Excellent - official source)

---

#### 3. Python `nba_api` Package - **RECOMMENDED APPROACH**
**Why**: Pre-built wrapper, easier than scraping, actively maintained
**Package**: `nba_api` (unofficial but widely used)
**What it provides**:
- Player stats (game-by-game, season totals)
- Team stats
- Game schedules
- Box scores
- Player info

**Advantages**:
- No scraping needed (uses NBA.com endpoints)
- Well-documented
- Actively maintained
- Handles rate limiting

**Limitations**:
- Unofficial (may break if NBA changes endpoints)
- May not have all advanced metrics
- Injury data may be limited

**Reliability**: ⭐⭐⭐⭐ (Very Good - but depends on package maintenance)

**Installation**: `pip install nba_api`

---

#### 4. ESPN / Team Websites - **FOR INJURIES**
**Why**: Good injury reporting, lineup confirmations
**What to Scrape**:
- Injury reports and status updates
- Lineup confirmations (starting lineups)
- Game previews (for context like rest days, back-to-backs)

**Frequency**: 
- Multiple times per day on game days
- Especially 2-4 hours before games

**Challenges**:
- ESPN has anti-scraping measures
- Structure may vary
- **Solution**: Use multiple sources, manual verification for critical games

**Reliability**: ⭐⭐⭐ (Good for injuries, but verify with official sources)

---

#### 5. Alternative: Stathead Basketball (basketball-reference.com premium)
**Why**: More advanced queries, but requires subscription
**Note**: May not be necessary for this project scope (current + previous season)

---

### Recommended Approach (Priority Order):

**Option A: Hybrid Approach (RECOMMENDED)**
1. **Primary**: Use `nba_api` Python package for most data
   - Player stats, game logs, schedules
   - Easiest to implement, most reliable
   
2. **Secondary**: Scrape Basketball Reference for:
   - Advanced metrics not in nba_api
   - Historical verification
   - Team defensive stats by position
   
3. **Tertiary**: Scrape NBA.com/ESPN for:
   - Injury reports (official NBA injury list)
   - Lineup confirmations

**Option B: Full Scraping Approach**
- If `nba_api` doesn't meet needs, scrape Basketball Reference primarily
- Use NBA.com for verification and injuries
- More complex but more control

**Decision**: Start with Option A (nba_api + selective scraping), fall back to Option B if needed

### Scraping Implementation:

**Tools**:
- Scrapy (for structured scraping)
- BeautifulSoup (for simpler pages)
- Selenium (if JavaScript rendering needed)
- Requests (for API-like endpoints)

**Best Practices**:
- Respect robots.txt
- Add delays between requests (1-2 seconds)
- Use user-agent headers
- Handle errors gracefully
- Cache responses when possible
- Log all scraping activities
- Monitor for site structure changes

**Scheduling**:
- **Daily at 6 AM**: Scrape previous day's game results
- **Every 2 hours on game days**: Check for injury updates
- **Daily at 8 AM**: Update upcoming game schedules
- **Weekly**: Full data validation and cleanup

---

## Prediction Algorithm (Distribution-Based Approach)

### Core Philosophy: Think in Distributions, Not Averages

**Key Principle**: Never predict a single value. Always predict a probability distribution of outcomes.

**Target Window**: 60-120 minutes before tipoff when lineups are confirmed. Recalculate distributions after confirmed lineups.

---

### Distribution Engine Architecture

#### Step 1: Build Base Distribution (Historical)

**Filter Historical Games**:
- Keep games where:
  - Minutes ≥ 75% of projected minutes
  - Role is the same (starter vs bench)
  - Season is current or previous season only
  - Minimum: 15 games (preferred: 30-50 games)

**Compute Raw Distribution**:
```python
import numpy as np
from scipy.stats import norm

# Get historical stat values
values = np.array([game.points for game in filtered_games])

# Calculate base statistics
base_mean = values.mean()
base_std = values.std(ddof=1)  # Sample standard deviation

# Calculate percentiles
percentiles = {
    10: np.percentile(values, 10),
    20: np.percentile(values, 20),
    25: np.percentile(values, 25),
    50: np.percentile(values, 50),  # Median
    75: np.percentile(values, 75),
    80: np.percentile(values, 80),
    90: np.percentile(values, 90)
}

# Store distribution object
PlayerStatDistribution = {
    'mean': base_mean,
    'std_dev': base_std,
    'percentiles': percentiles,
    'sample_size': len(values)
}
```

---

#### Step 2: Adjust the Mean (μ) - Contextual Factors

**Apply Multiplicative Modifiers** (clamped to prevent overconfidence):

```python
# Minutes Factor
minutes_factor = projected_minutes / historical_avg_minutes
minutes_factor = clamp(minutes_factor, 0.85, 1.20)

# Pace Factor
game_pace = (opponent_pace + team_pace) / 2
league_avg_pace = 100  # example
pace_factor = game_pace / league_avg_pace
pace_factor = clamp(pace_factor, 0.85, 1.20)

# Defense Factor (Opponent vs Position)
opp_allowed_vs_pos = get_team_position_defense(opponent, player_position)
league_avg_vs_pos = get_league_avg_by_position(player_position)
defense_factor = opp_allowed_vs_pos / league_avg_vs_pos
defense_factor = clamp(defense_factor, 0.85, 1.20)

# Usage Factor (if teammate injured)
if teammate_injured:
    projected_usage = calculate_redistributed_usage(player, injured_teammate)
    usage_factor = projected_usage / historical_usage
    usage_factor = clamp(usage_factor, 0.85, 1.25)
else:
    usage_factor = 1.0

# Home/Away Factor
if is_home:
    home_factor = 1.05
else:
    home_factor = 0.97

# Final Adjusted Mean
adjusted_mean = (base_mean * 
                 minutes_factor * 
                 pace_factor * 
                 defense_factor * 
                 usage_factor * 
                 home_factor)
```

---

#### Step 3: Adjust the Variance (σ) - The Secret Sauce

**Most systems ignore this. This is what makes your model powerful.**

**Apply Volatility Multipliers**:

```python
# Base volatility
base_volatility = 1.0

# Minutes Volatility
if minutes_are_locked:  # Locked starter
    minutes_volatility = 0.90
elif minutes_are_unstable:  # Bench player, inconsistent role
    minutes_volatility = 1.20
else:
    minutes_volatility = 1.00

# Usage Volatility
if usage_depends_on_others:  # High-usage but depends on star being out
    usage_volatility = 1.25
elif usage_is_stable:
    usage_volatility = 0.90
else:
    usage_volatility = 1.00

# Blowout Risk
if blowout_risk_high:  # Large point spread
    blowout_volatility = 1.15
else:
    blowout_volatility = 1.00

# Final Adjusted Standard Deviation
adjusted_std = base_std * minutes_volatility * usage_volatility * blowout_volatility

# Cap variance
adjusted_std = clamp(adjusted_std, base_std * 0.8, base_std * 1.5)
```

---

#### Step 4: Reconstruct Adjusted Distribution

**Create Normal Distribution** (good enough for props):

```python
from scipy.stats import norm

# Create distribution
dist = norm(loc=adjusted_mean, scale=adjusted_std)

# Recalculate percentiles from adjusted distribution
adjusted_percentiles = {
    10: dist.ppf(0.10),
    20: dist.ppf(0.20),
    25: dist.ppf(0.25),
    50: dist.ppf(0.50),  # Median
    75: dist.ppf(0.75),
    80: dist.ppf(0.80),
    90: dist.ppf(0.90)
}
```

---

#### Step 5: Define Safe / Standard / Long Shot Formally

**Safe Bet** (Target: 70-75% hit rate):
```python
safe_line = dist.ppf(0.25)  # 25th percentile
safe_probability = 1 - dist.cdf(safe_line)  # ~75%
```

**Standard Bet** (Target: ~50%):
```python
standard_line = dist.ppf(0.50)  # Median
standard_probability = 1 - dist.cdf(standard_line)  # ~50%
```

**Long Shot** (Target: 15-20% hit rate, high payout):
```python
long_shot_line = dist.ppf(0.85)  # 85th percentile
long_shot_probability = 1 - dist.cdf(long_shot_line)  # ~15%
```

---

#### Step 6: Pass Rules (When to NOT Recommend)

**Critical Guardrails** - System must say "NO BET" if:

```python
def should_pass(player, distribution, context):
    # Sample size too small
    if distribution['sample_size'] < 15:
        return True, "Insufficient sample size"
    
    # Minutes too low
    if projected_minutes < 20:
        return True, "Projected minutes too low"
    
    # Usage change too dramatic
    if abs(usage_change) > 0.25:  # >25% change
        return True, "Usage change too uncertain"
    
    # Injury uncertainty
    if player_injury_status == "Questionable" and no_confirmation:
        return True, "Injury uncertainty"
    
    # Variance too high relative to mean
    if distribution['std_dev'] / distribution['mean'] > 0.40:  # >40% CV
        return True, "Too volatile"
    
    return False, None
```

**Passing is a feature, not a failure.**

---

#### Step 7: Compare Against Sportsbook Lines (Advanced)

**For each sportsbook line**:

```python
# Get sportsbook line
book_line = get_sportsbook_line(player, stat_type, game)

# Calculate probability of going over
p_over = 1 - dist.cdf(book_line)

# Convert book odds to implied probability
book_odds = get_book_odds(book_line)
implied_prob = odds_to_probability(book_odds)

# Calculate edge
edge = p_over - implied_prob

# Flag if edge exists
if edge >= 0.05:  # 5% edge
    recommendation = "BET"
    confidence = "HIGH" if edge >= 0.10 else "MEDIUM"
else:
    recommendation = "PASS"
```

---

#### Step 8: Output Format

**For each player, show**:

```
Player: LeBron James (SF) - Lakers vs Rockets

PTS Distribution:
  Mean: 24.5
  Std Dev: 4.2
  Percentiles:
    25th: 21.2 (Safe: Over 21.5 → 73% probability)
    50th: 24.5 (Standard: Over 24.5 → 52% probability)
    85th: 28.8 (Long Shot: Over 28.5 → 17% probability)

Confidence: HIGH
Volatility: LOW
Recommendation: SAFE ONLY

Key Factors:
  • Season avg: 25.3 ppg
  • Rockets rank 28th vs SF (weak defense)
  • Locked starter, stable minutes
  • No injury concerns
```

---

### Minutes & Usage Redistribution Engine

**When a starter is injured, redistribute minutes and usage**:

```python
def redistribute_when_injured(injured_player, team, position):
    # Historical pattern: When this player was out, who got more minutes?
    historical_patterns = get_injury_impact_history(injured_player, position)
    
    # Find backup at same position
    backup = find_backup_player(team, position)
    
    # Calculate expected minutes increase
    avg_minutes_increase = historical_patterns['avg_minutes_increase']
    projected_backup_minutes = backup.avg_minutes + avg_minutes_increase
    
    # Calculate usage redistribution
    injured_usage = injured_player.usage_rate
    # Typically: 60-70% of injured player's usage goes to backup
    usage_redistribution = injured_usage * 0.65
    projected_backup_usage = backup.usage_rate + usage_redistribution
    
    return {
        'backup_player': backup,
        'projected_minutes': projected_backup_minutes,
        'projected_usage': projected_backup_usage,
        'confidence': historical_patterns['sample_size'] >= 5
    }
```

---

### Why This Approach Works

1. **Models uncertainty, not just averages** - Accounts for variance
2. **Waits for confirmed lineups** - Recalculates when lineups are known
3. **Doesn't force bets** - Pass rules prevent bad bets
4. **Exploits variance mispricing** - Books often misprice volatility
5. **Professional-grade** - This is how serious prop bettors think

---

### Advanced Features (Future Enhancements)

**On/Off Defensive Splits**:
- Calculate how opposing players perform when specific defender is on court vs off
- More granular than team vs position defense

**Machine Learning Models** (After heuristics work):
- Use distribution features as ML inputs
- Predict distributions, not point values
- Compare ML vs heuristic performance

**Betting Line Integration**:
- Scrape or use paid API for sportsbook lines
- Compare distributions to lines
- Flag edges automatically

---

## User Interface Design

### Main Dashboard

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  NBA Betting Analytics                    [Date Picker] │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Today's Games (5)                                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Lakers @ Rockets - 8:00 PM ET                   │   │
│  │ [View All Picks] [3 Safe] [2 Long Shots]        │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Warriors @ Celtics - 7:30 PM ET                 │   │
│  │ [View All Picks] [2 Safe] [3 Long Shots]        │   │
│  └─────────────────────────────────────────────────┘   │
│  ...                                                    │
│                                                           │
│  Quick Stats:                                            │
│  • Total Safe Picks Today: 12                           │
│  • Total Long Shots: 8                                  │
│  • Injury Updates: 3 players questionable               │
└─────────────────────────────────────────────────────────┘
```

### Game Detail View

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  Lakers @ Rockets - Dec 15, 2024 - 8:00 PM ET            │
│  [← Back to Games]                                       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Safe Picks (High Likelihood)                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LeBron James (SF) - Lakers                      │   │
│  │ Points Distribution:                            │   │
│  │   Safe: Over 21.5 (73% probability)            │   │
│  │   Standard: Over 24.5 (52% probability)        │   │
│  │   Long Shot: Over 28.5 (17% probability)       │   │
│  │ Mean: 24.5 | Std Dev: 4.2                       │   │
│  │ Confidence: HIGH | Volatility: LOW               │   │
│  │ [View Details] [Create Play]                    │   │
│  │                                                  │   │
│  │ Key Factors:                                    │   │
│  │ • Season avg: 25.3 ppg                          │   │
│  │ • Rockets rank 28th vs SF (weak defense)        │   │
│  │ • Locked starter, stable minutes                │   │
│  │ • No injury concerns                            │   │
│  └─────────────────────────────────────────────────┘   │
│  ... (more safe picks)                                   │
│                                                           │
│  Long Shots (High Upside)                                │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Rui Hachimura (PF) - Lakers                     │   │
│  │ Points Distribution:                            │   │
│  │   Safe: Over 12.5 (68% probability)            │   │
│  │   Standard: Over 16.5 (48% probability)        │   │
│  │   Long Shot: Over 22.5 (18% probability)       │   │
│  │ Mean: 16.8 | Std Dev: 5.1                       │   │
│  │ Confidence: MEDIUM | Volatility: HIGH            │   │
│  │ [View Details] [Create Play]                    │   │
│  │                                                  │   │
│  │ Opportunity:                                     │   │
│  │ • AD questionable - if out, +8-10 minutes       │   │
│  │ • Rockets weak vs PF (rank 26th)                │   │
│  │ • Recent form: 18+ in 2 of last 5              │   │
│  │                                                  │   │
│  │ Risk: If AD plays, limited minutes              │   │
│  │ Note: High volatility - long shot only        │   │
│  └─────────────────────────────────────────────────┘   │
│  ... (more long shots)                                   │
│                                                           │
│  Injury Report                                           │
│  • Anthony Davis (Lakers) - Questionable (ankle)         │
│  • Jalen Green (Rockets) - Probable (knee)              │
└─────────────────────────────────────────────────────────┘
```

### Pick Detail View

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  LeBron James - Points Prediction                        │
│  Lakers @ Rockets - Dec 15, 2024                         │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Prediction: 24-28 points                                │
│  Likelihood: 82%                                         │
│  Bet Type: Safe Bet                                      │
│                                                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Recent Form (Last 10 Games)                     │   │
│  │ [Chart showing points per game]                 │   │
│  └─────────────────────────────────────────────────┘   │
│                                                           │
│  Key Factors:                                            │
│  • Season Average: 25.3 ppg                              │
│  • Last 10 Games Avg: 25.8 ppg                           │
│  • Last 5 Games Avg: 26.2 ppg                            │
│                                                           │
│  Matchup Analysis:                                       │
│  • Opponent: Rockets (28th vs SF)                        │
│  • Rockets allow 24.5 ppg to SF (league avg: 18.2)      │
│  • Head-to-Head: 26.1 ppg vs Rockets (5 games)           │
│                                                           │
│  Context:                                                │
│  • Home/Away: Away                                       │
│  • Pace: Fast (both teams top 10 pace)                   │
│  • Injury Status: Healthy                                │
│                                                           │
│  Historical Performance vs Rockets:                       │
│  Game 1: 28 points                                       │
│  Game 2: 24 points                                       │
│  Game 3: 27 points                                       │
│  Game 4: 25 points                                       │
│  Game 5: 26 points                                       │
└─────────────────────────────────────────────────────────┘
```

### Filters & Search

**Available Filters**:
- Date range
- Teams (select specific teams)
- Stat category (Points, Rebounds, Assists, Minutes)
- Likelihood threshold (e.g., "Show only 75%+ picks")
- Bet type (Safe bets only, Long shots only, Both)
- Position
- Player name (search)

---

### My Plays (Play Tracking)

**Purpose**: View and manage all saved betting plays

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│  My Plays                                    [Filter] [Sort]│
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Filter: [All] [Pending] [Hit] [Miss]                    │
│                                                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │ LeBron James - Points                           │   │
│  │ Lakers @ Rockets - Dec 15, 2024 - 8:00 PM      │   │
│  │ Bet: Over 24.5 points                           │   │
│  │ Predicted: 24-28 points (82% likelihood)       │   │
│  │ Status: [Pending] [Mark as Hit] [Mark as Miss]  │   │
│  │ Notes: Safe bet, weak defense                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Anthony Davis - Rebounds                         │   │
│  │ Lakers @ Rockets - Dec 15, 2024 - 8:00 PM      │   │
│  │ Bet: Over 10.5 rebounds                          │   │
│  │ Predicted: 10-13 rebounds (75% likelihood)      │   │
│  │ Status: ✅ Hit (Actual: 12 rebounds)            │   │
│  │ Notes: Strong matchup                            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                           │
│  Performance Summary:                                    │
│  • Total Plays: 45                                       │
│  • Pending: 5                                            │
│  • Hits: 28 (70%)                                        │
│  • Misses: 12 (30%)                                      │
└─────────────────────────────────────────────────────────┘
```

**Features**:
- View all saved plays (chronological or by status)
- Filter by status (Pending, Hit, Miss)
- Filter by date range
- Quick actions: Mark as Hit/Miss, Edit (if pending), Delete
- Performance summary (win rate, recent trends)
- Click play to see full details and prediction reasoning

**Create Play Flow**:
1. View recommendation on game detail page
2. Click "Create Play" button
3. Modal/form appears:
   - Player and game pre-filled
   - Stat type pre-filled
   - Enter bet line (e.g., "Over 24.5")
   - Add optional notes
   - Click "Save Play"
4. Play appears in "My Plays" with "Pending" status
5. After game, mark as Hit or Miss
6. System tracks actual result vs. prediction

---

## Data Update & Maintenance

### Update Schedule:

**Daily Updates** (6:00 AM):
- Scrape previous day's game results
- Update player statistics
- Update team defensive rankings
- Calculate new matchup data

**Game Day Updates** (Every 2 hours, starting 8:00 AM):
- Check for injury updates
- Update game statuses
- Refresh predictions if new data available

**Weekly Updates** (Sunday night):
- Full data validation
- Clean up old data (beyond 2 seasons)
- Recalculate all aggregated statistics
- Performance optimization

### Data Validation:

**Checks to Perform**:
- Missing game data
- Inconsistent statistics (points don't match FGM, etc.)
- Duplicate entries
- Outlier detection (flag unusual stats for review)
- Injury report accuracy (cross-reference multiple sources)

---

## Implementation Phases

### Phase 1: Foundation & Data Collection
**Duration**: 2-3 weeks

**Tasks**:
- [ ] Set up development environment
- [ ] Design and create database schema
- [ ] Set up PostgreSQL database
- [ ] Build basic scraping infrastructure
- [ ] Scrape current season data (game-by-game)
- [ ] Scrape previous season data (game-by-game)
- [ ] Set up data validation pipeline
- [ ] Create basic API endpoints (FastAPI)
- [ ] Set up scheduled tasks (Celery)

**Deliverables**:
- Database with current + previous season data
- Working scraping pipeline
- Basic API to query data

---

### Phase 2: Analytics Engine
**Duration**: 2-3 weeks

**Tasks**:
- [ ] Build team position defense calculator
- [ ] Build player-team matchup analyzer
- [ ] Calculate aggregated statistics
- [ ] Build home/away split calculators
- [ ] Implement recent form calculations
- [ ] Create pace analysis
- [ ] Build data aggregation jobs

**Deliverables**:
- Team defensive rankings by position
- Player matchup histories
- All aggregated analytics data

---

### Phase 3: Injury Tracking System
**Duration**: 1-2 weeks

**Tasks**:
- [ ] Build injury scraping infrastructure
- [ ] Create injury impact analyzer
- [ ] Build historical injury impact database
- [ ] Calculate minutes redistribution patterns
- [ ] Create backup player opportunity detector
- [ ] Set up real-time injury monitoring

**Deliverables**:
- Current injury database
- Injury impact analysis system
- Historical injury patterns

---

### Phase 4: Prediction Engine
**Duration**: 2-3 weeks

**Tasks**:
- [ ] Build baseline prediction calculator
- [ ] Implement opponent adjustment logic
- [ ] Build head-to-head adjustment
- [ ] Create injury context adjustments
- [ ] Implement range generation
- [ ] Build likelihood scoring system
- [ ] Create safe bet classifier
- [ ] Create long shot classifier
- [ ] Test and tune prediction accuracy

**Deliverables**:
- Working prediction engine
- Safe bet identification
- Long shot identification

---

### Phase 5: Frontend Development
**Duration**: 2-3 weeks

**Tasks**:
- [ ] Set up React project
- [ ] Build main dashboard
- [ ] Create game list view
- [ ] Build game detail view
- [ ] Create pick detail view
- [ ] Implement filters and search
- [ ] Add data visualizations (charts)
- [ ] Style with Tailwind CSS
- [ ] Make responsive (mobile-friendly)

**Deliverables**:
- Complete UI for viewing picks
- All user-facing features

---

### Phase 6: Integration & Testing
**Duration**: 1-2 weeks

**Tasks**:
- [ ] Connect frontend to backend API
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] Bug fixes
- [ ] User acceptance testing
- [ ] Documentation

**Deliverables**:
- Fully functional application
- Documentation

---

### Phase 7: Local Development Setup & Final Integration
**Duration**: 1 week

**Tasks**:
- [ ] Set up local development environment
- [ ] Configure PostgreSQL database locally
- [ ] Set up backend to run locally (FastAPI dev server)
- [ ] Set up frontend to run locally (React dev server)
- [ ] Configure data scraping scripts to run locally
- [ ] Set up local task scheduler (for daily data updates)
- [ ] Create setup documentation (README with installation steps)
- [ ] Test end-to-end workflow locally
- [ ] Create data backup procedures

**Deliverables**:
- Fully functional local application
- Setup documentation
- Local development environment ready

---

## Success Metrics & Validation

### Prediction Accuracy Goals:

**Safe Bets**:
- Target: 75%+ of predictions should fall within predicted range
- Track: Hit rate over time
- Monitor: Which factors are most predictive

**Long Shots**:
- Target: 40-50% hit rate (acceptable for high-upside bets)
- Track: Average upside when they hit
- Monitor: Which opportunities are most valuable

### Data Quality Metrics:
- Completeness: 95%+ of games have full data
- Accuracy: Cross-reference with official NBA stats
- Timeliness: Injury updates within 2 hours of release

### System Performance:
- API response time: <500ms for dashboard
- Data update latency: <1 hour for game results
- Scraping success rate: 95%+

---

## Risk Factors & Considerations

### Data Quality Risks:
- **Scraping failures**: Sites change structure, rate limiting
  - *Mitigation*: Multiple data sources, error handling, monitoring

- **Missing data**: Some games may have incomplete stats
  - *Mitigation*: Data validation, flagging incomplete records

- **Injury report accuracy**: Reports can be vague or change
  - *Mitigation*: Multiple sources, update frequently, conservative estimates

### Prediction Accuracy Risks:
- **Small sample sizes**: New players, rare matchups
  - *Mitigation*: Lower confidence scores, wider ranges, flag low-sample picks

- **Unpredictable events**: Ejections, blowouts, rest days
  - *Mitigation*: Game script analysis, monitor for late-breaking news

- **Model assumptions**: Algorithm may not capture all factors
  - *Mitigation*: Continuous improvement, track accuracy, adjust weights

### Technical Risks:
- **Scraping blocks**: Sites may block scrapers
  - *Mitigation*: Respect rate limits, use proxies if needed, have backup sources

- **Database performance**: Large datasets, complex queries
  - *Mitigation*: Proper indexing, query optimization, caching

---

## Future Enhancements (Post-MVP)

### Advanced Features:
1. **Machine Learning Models**: Train ML models on historical data
2. **Real-time Game Tracking**: Live updates during games
3. **Historical Bet Tracking**: Track your bets and ROI
4. **Custom Alerts**: Get notified when specific conditions are met
5. **Comparison Tool**: Compare multiple players side-by-side
6. **Trend Analysis**: Identify trending players/teams
7. **Weather/Venue Factors**: Account for travel, rest days, altitude
8. **Playoff Adjustments**: Different models for playoff games
9. **User Accounts**: Save favorite players, custom filters
10. **Export Functionality**: Export picks to CSV/PDF

---

## Decisions Made & Remaining Questions

### ✅ Decisions Made:

1. **Data Sources**: 
   - Primary: `nba_api` Python package (easiest, most reliable)
   - Secondary: Basketball Reference scraping (for advanced metrics)
   - Tertiary: NBA.com/ESPN for injury reports
   - **Status**: Research complete, approach decided

2. **Deployment**: 
   - Local development only (personal use)
   - No cloud hosting needed
   - **Status**: Decided

3. **UI Approach**: 
   - Start simple, iterate
   - Must include play creation and tracking
   - **Status**: Requirements defined

4. **Workflow**: 
   - Create plays from recommendations
   - Save plays manually
   - Track outcomes manually after games
   - **Status**: Defined

### ⚠️ Remaining Questions (Can be decided during development):

1. **Prediction Tuning**: How should we weight different factors? 
   - *Answer*: Start with proposed weights, tune based on results
   - Can adjust during testing phase

2. **UI Design Details**: Specific color scheme, exact layout preferences?
   - *Answer*: Start with clean, simple design. Can refine later.

3. **Update Frequency**: How often to refresh data?
   - *Answer*: Daily updates sufficient for personal use. Can adjust if needed.

4. **Historical Validation**: Should we backtest predictions?
   - *Answer*: Good idea, but can do this after MVP is working

---

## Next Steps

1. **Review this document** - Ensure all requirements are captured
2. **Answer open questions** - Finalize any remaining decisions
3. **Set up development environment** - Install tools, set up repos
4. **Begin Phase 1** - Start with database and data collection

---

*Document Version: 2.1*
*Last Updated: Based on final clarifications (data sources, local dev, play tracking)*
*Status: Complete - Ready to begin development*
