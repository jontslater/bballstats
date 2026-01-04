# NBA Betting Analytics Platform - Execution Plan

## Overview
This document provides a systematic, step-by-step build order for implementing the NBA Betting Analytics Platform. Follow phases sequentially, completing all tasks in each phase before moving to the next.

**Estimated Total Time**: 10-14 weeks (depending on experience level)

## Key Approach: Distribution-Based Predictions

**Important**: This system uses **probability distributions**, not simple averages or ranges. 

**Core Principles**:
- Predict probability distributions (mean, std dev, percentiles) for each stat
- Adjust both mean (μ) and variance (σ) based on context
- Define Safe/Standard/Long Shot bets using percentiles (25th, 50th, 85th)
- Implement pass rules - system must say "NO BET" when uncertain
- Recalculate distributions when lineups are confirmed (60-120 min before tipoff)
- Redistribute minutes/usage when starters are injured

**This is a professional-grade approach** used by serious prop bettors and analytics teams.

---

## Prerequisites Checklist

Before starting, ensure you have:
- [ ] Python 3.9+ installed
- [ ] Node.js 16+ and npm installed
- [ ] PostgreSQL installed and running locally
- [ ] Git installed
- [ ] Code editor/IDE set up
- [ ] Basic understanding of Python, SQL, and React

---

## Phase 1: Project Setup & Database Foundation
**Duration**: 3-5 days  
**Goal**: Set up development environment and create database schema

### Step 1.1: Initialize Project Structure
**Time**: 1-2 hours

```bash
# Create project directories
mkdir -p backend frontend scripts data
cd backend
mkdir -p app/models app/api app/services app/scrapers
cd ../frontend
mkdir -p src/components src/pages src/services src/utils
```

**Tasks**:
- [ ] Create root directory structure
- [ ] Initialize Git repository (`git init`)
- [ ] Create `.gitignore` files (Python, Node.js, database)
- [ ] Create root `README.md` with setup instructions

**Deliverable**: Project structure ready

---

### Step 1.2: Set Up Backend Environment
**Time**: 2-3 hours

**Tasks**:
- [ ] Create `backend/requirements.txt` with dependencies:
  ```
  fastapi==0.104.1
  uvicorn==0.24.0
  sqlalchemy==2.0.23
  psycopg2-binary==2.9.9
  pandas==2.1.3
  python-dotenv==1.0.0
  pydantic==2.5.0
  requests==2.31.0
  beautifulsoup4==4.12.2
  nba-api==1.2.1
  schedule==1.2.0
  ```
- [ ] Create virtual environment: `python -m venv venv`
- [ ] Activate virtual environment
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `backend/.env` file for database connection
- [ ] Create `backend/app/__init__.py`
- [ ] Create `backend/app/main.py` (basic FastAPI app)

**Deliverable**: Backend environment ready, FastAPI app runs

---

### Step 1.3: Set Up Frontend Environment
**Time**: 1-2 hours

**Tasks**:
- [ ] Navigate to `frontend/` directory
- [ ] Initialize React app: `npx create-react-app . --template typescript` (or use Vite)
- [ ] Install additional dependencies:
  ```bash
  npm install axios react-router-dom recharts tailwindcss
  ```
- [ ] Set up Tailwind CSS (if using)
- [ ] Create basic folder structure
- [ ] Test that app runs: `npm start`

**Deliverable**: Frontend environment ready, React app runs

---

### Step 1.4: Set Up PostgreSQL Database
**Time**: 2-3 hours

**Tasks**:
- [ ] Ensure PostgreSQL is installed and running
- [ ] Create database: `CREATE DATABASE nba_betting;`
- [ ] Create database user (optional, can use default)
- [ ] Test connection from Python
- [ ] Create `backend/app/database.py` with SQLAlchemy setup:
  ```python
  from sqlalchemy import create_engine
  from sqlalchemy.ext.declarative import declarative_base
  from sqlalchemy.orm import sessionmaker
  import os
  from dotenv import load_dotenv
  
  load_dotenv()
  
  DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/nba_betting")
  
  engine = create_engine(DATABASE_URL)
  SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
  Base = declarative_base()
  ```

**Deliverable**: Database created, connection working

---

### Step 1.5: Create Database Models (SQLAlchemy)
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `backend/app/models/__init__.py`
- [ ] Create `backend/app/models/player.py` (Player model)
- [ ] Create `backend/app/models/team.py` (Team model)
- [ ] Create `backend/app/models/season.py` (Season model)
- [ ] Create `backend/app/models/game.py` (Game model)
- [ ] Create `backend/app/models/player_game_stat.py` (PlayerGameStat model)
- [ ] Create `backend/app/models/injury.py` (Injury model)
- [ ] Create `backend/app/models/team_position_defense.py` (TeamPositionDefense model)
- [ ] Create `backend/app/models/player_team_matchup.py` (PlayerTeamMatchup model)
- [ ] Create `backend/app/models/injury_impact_history.py` (InjuryImpactHistory model)
- [ ] Create `backend/app/models/prediction.py` (Prediction model)
  - **Important**: Must include all distribution fields:
    - distribution_mean, distribution_std_dev
    - All percentiles (10, 20, 25, 50, 75, 80, 85, 90)
    - Safe/Standard/Long Shot lines and probabilities
    - Pass rules fields (pass_reason, bet_type)
    - Confidence and volatility levels
    - See PROJECT_OUTLINE.md for full schema
- [ ] Create `backend/app/models/game_schedule.py` (GameSchedule model)
- [ ] Create `backend/app/models/user_play.py` (UserPlay model)
- [ ] Update `backend/app/models/__init__.py` to import all models
- [ ] Create migration script or use Alembic to create tables
- [ ] Run initial migration to create all tables
- [ ] Verify tables created in PostgreSQL

**Deliverable**: All database models created, tables exist in database

---

### Step 1.6: Create Database Seeding Script (Basic Data)
**Time**: 2-3 hours

**Tasks**:
- [ ] Create `scripts/seed_teams.py` - Add all 30 NBA teams
- [ ] Create `scripts/seed_seasons.py` - Add current and previous season
- [ ] Test scripts run successfully
- [ ] Verify data in database

**Deliverable**: Basic reference data (teams, seasons) in database

---

**Phase 1 Checkpoint**: 
- ✅ Project structure exists
- ✅ Backend and frontend environments set up
- ✅ Database created with all tables
- ✅ Basic reference data seeded
- ✅ Can connect to database from Python
- ✅ FastAPI app runs
- ✅ React app runs

**Before moving to Phase 2**: Test that you can query the database from FastAPI and display data in React.

---

## Phase 2: Data Collection Infrastructure
**Duration**: 1-2 weeks  
**Goal**: Build data scraping and collection system

### Step 2.1: Set Up NBA API Integration
**Time**: 3-4 hours

**Tasks**:
- [ ] Install and test `nba_api` package
- [ ] Create `backend/app/scrapers/__init__.py`
- [ ] Create `backend/app/scrapers/nba_api_client.py`:
  - Test connection to NBA API
  - Create functions to fetch players
  - Create functions to fetch teams
  - Create functions to fetch game schedules
  - Create functions to fetch game results
  - Handle errors and rate limiting
- [ ] Test fetching current season data
- [ ] Test fetching previous season data

**Deliverable**: NBA API client working, can fetch basic data

---

### Step 2.2: Create Player Data Collection Script
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `scripts/collect_players.py`:
  - Fetch all active players from NBA API
  - Store player basic info (name, position, team, etc.)
  - Handle duplicates
  - Update existing players
- [ ] Test script on small subset
- [ ] Run full collection for current season
- [ ] Verify players in database

**Deliverable**: Player data collection script working

---

### Step 2.3: Create Game Schedule Collection Script
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `scripts/collect_schedules.py`:
  - Fetch game schedules for current season
  - Fetch game schedules for previous season
  - Store game dates, teams, times
  - Handle game status updates
- [ ] Test script
- [ ] Run for current and previous season
- [ ] Verify schedules in database

**Deliverable**: Game schedule collection working

---

### Step 2.4: Create Game Results Collection Script
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `scripts/collect_game_results.py`:
  - Fetch completed game results
  - Fetch box scores for each game
  - Store game-level stats (scores, pace)
  - Store player-level stats (points, rebounds, assists, minutes, etc.)
  - Handle missing data gracefully
  - Update game status
- [ ] Test on single game
- [ ] Test on multiple games
- [ ] Run for previous season (full collection)
- [ ] Set up daily collection for current season
- [ ] Verify data quality (check for missing games, outliers)

**Deliverable**: Game results collection working, historical data loaded

---

### Step 2.5: Set Up Basketball Reference Scraping (Optional/Advanced)
**Time**: 6-8 hours (if needed)

**Tasks**:
- [ ] Create `backend/app/scrapers/basketball_reference.py`:
  - Set up BeautifulSoup
  - Create functions to scrape player game logs
  - Create functions to scrape team stats
  - Handle rate limiting (2-3 second delays)
  - Handle errors and retries
- [ ] Test scraping single player
- [ ] Test scraping team defensive stats
- [ ] Create validation to compare with NBA API data
- [ ] Use as backup/verification source

**Deliverable**: Basketball Reference scraper working (if needed)

---

### Step 2.6: Create Data Validation Scripts
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `scripts/validate_data.py`:
  - Check for missing games
  - Check for missing player stats
  - Validate stat consistency (points = FGM calculations, etc.)
  - Flag outliers for review
  - Generate data quality report
- [ ] Run validation after data collection
- [ ] Fix any data issues found

**Deliverable**: Data validation system working

---

### Step 2.7: Set Up Update Scripts
**Time**: 2-3 hours

**Tasks**:
- [ ] Create `scripts/update_all.py` (master update script):
  - Updates game results
  - Updates player statistics
  - Updates schedules
  - Recalculates analytics
  - Updates injuries
  - Regenerates predictions
  - Comprehensive logging
- [ ] Create `scripts/quick_update.py` (fast version):
  - Just updates yesterday's games
  - Regenerates today's predictions
  - For use before games (60-120 min before tipoff)
- [ ] Test both scripts manually
- [ ] Create `scripts/README.md` with usage instructions
- [ ] Choose automation method (optional):
  - **Option A: Cron Job (Recommended for Mac/Linux)**
    - Set up cron job to run daily at 6 AM
    - Command: `0 6 * * * cd /path/to/bballstats && /path/to/venv/bin/python scripts/update_all.py`
  - **Option B: Manual (Simplest - Recommended)**
    - Just run `python scripts/update_all.py` once per day
    - Run `python scripts/quick_update.py` before games
- [ ] Test scripts end-to-end

**Deliverable**: Simple update scripts working

**Usage**:
- Daily: `python scripts/update_all.py`
- Before games: `python scripts/quick_update.py`

---

**Phase 2 Checkpoint**:
- ✅ Can collect player data
- ✅ Can collect game schedules
- ✅ Can collect game results and box scores
- ✅ Historical data (previous season) loaded
- ✅ Current season data updating
- ✅ Data validation working
- ✅ Daily update process set up

**Before moving to Phase 3**: Verify you have at least one full season of game-by-game data in the database.

---

## Phase 3: Analytics Engine - Core Calculations
**Duration**: 1-2 weeks  
**Goal**: Build analytics calculations for team defense and matchups

### Step 3.1: Create Team Position Defense Calculator
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `backend/app/services/__init__.py`
- [ ] Create `backend/app/services/team_defense_calculator.py`:
  - Function to calculate points allowed by position
  - Function to calculate rebounds allowed by position
  - Function to calculate assists allowed by position
  - Function to calculate minutes allowed by position
  - Calculate home/away splits
  - Calculate recent form (last 5, 10, 20 games)
  - Calculate defensive rankings (1-30)
  - Store results in `team_position_defense` table
- [ ] Test on single team/position
- [ ] Run for all teams and positions
- [ ] Verify calculations make sense

**Deliverable**: Team position defense calculator working

---

### Step 3.2: Create Player-Team Matchup Analyzer
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `backend/app/services/matchup_analyzer.py`:
  - Function to find all games where player X faced team Y
  - Calculate averages (points, rebounds, assists, minutes)
  - Calculate last 5 games average
  - Store results in `player_team_matchups` table
- [ ] Test on sample players
- [ ] Run for all players vs. all teams (current + previous season)
- [ ] Handle cases with small sample sizes

**Deliverable**: Player-team matchup analyzer working

---

### Step 3.3: Create Recent Form Calculator
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `backend/app/services/form_calculator.py`:
  - Function to calculate last 5 games average
  - Function to calculate last 10 games average
  - Function to calculate last 15 games average
  - Function to detect trends (improving/declining)
  - Function to calculate standard deviation
- [ ] Test on sample players
- [ ] Integrate with prediction engine (will use in Phase 4)

**Deliverable**: Recent form calculator working

---

### Step 3.4: Create Pace Calculator
**Time**: 2-3 hours

**Tasks**:
- [ ] Create `backend/app/services/pace_calculator.py`:
  - Function to calculate team pace (possessions per game)
  - Function to calculate game pace
  - Store pace data
- [ ] Calculate pace for all teams
- [ ] Calculate pace for all games

**Deliverable**: Pace calculator working

---

### Step 3.5: Create Aggregation Service
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `backend/app/services/aggregation_service.py`:
  - Function to run all analytics calculations
  - Function to update all aggregated data
  - Schedule regular updates
- [ ] Test full aggregation run
- [ ] Set up to run after daily data updates

**Deliverable**: Aggregation service working

---

**Phase 3 Checkpoint**:
- ✅ Team position defense stats calculated
- ✅ Player-team matchup histories calculated
- ✅ Recent form calculations working
- ✅ Pace calculations working
- ✅ All analytics data aggregated and stored

**Before moving to Phase 4**: Verify analytics data looks correct (e.g., weak defensive teams rank low, strong matchups show higher averages).

---

## Phase 4: Injury Tracking System
**Duration**: 1 week  
**Goal**: Build injury tracking and impact analysis

### Step 4.1: Create Injury Data Collection
**Time**: 6-8 hours

**Tasks**:
- [ ] Research injury data sources (NBA.com, ESPN, etc.)
- [ ] Create `backend/app/scrapers/injury_scraper.py`:
  - Function to scrape/collect injury reports
  - Parse injury status (Out, Doubtful, Questionable, etc.)
  - Store in `injuries` table
  - Handle updates to existing injuries
- [ ] Test on sample data
- [ ] Set up regular collection (multiple times per day on game days)

**Deliverable**: Injury data collection working

---

### Step 4.2: Create Injury Impact Analyzer
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `backend/app/services/injury_impact_analyzer.py`:
  - Function to identify when starters are injured
  - Function to find backup players at same position
  - Function to calculate historical minutes increase for backups
  - Function to calculate stat increases for backups
  - Store in `injury_impact_history` table
- [ ] Analyze historical injury patterns
- [ ] Build database of injury impact patterns

**Deliverable**: Injury impact analyzer working

---

### Step 4.3: Create Injury Context Service
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `backend/app/services/injury_context.py`:
  - Function to get current injuries for a team
  - Function to identify affected players
  - Function to identify beneficiary players
  - Function to estimate minutes impact
- [ ] Test with current injury data
- [ ] Integrate with prediction engine (will use in Phase 5)

**Deliverable**: Injury context service working

---

**Phase 4 Checkpoint**:
- ✅ Injury data collection working
- ✅ Historical injury impact patterns analyzed
- ✅ Can identify injury opportunities
- ✅ Injury context available for predictions
- ✅ Lineup confirmation tracking working

**Before moving to Phase 5**: Test that injury data is being collected, impact analysis is working, and lineups can be tracked.

---

## Phase 5: Distribution-Based Prediction Engine
**Duration**: 2-3 weeks  
**Goal**: Build distribution-based prediction system (not just averages)

### Step 5.1: Create Base Distribution Calculator
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `backend/app/services/distribution_engine.py`
- [ ] Implement historical game filtering:
  - Filter by minutes (≥75% of projected)
  - Filter by role (starter vs bench)
  - Filter by season (current + previous only)
  - Minimum 15 games required
- [ ] Calculate base distribution:
  - Mean (μ)
  - Standard deviation (σ)
  - Percentiles (10, 20, 25, 50, 75, 80, 90)
- [ ] Use scipy.stats for distribution calculations
- [ ] Test on sample players
- [ ] Verify distributions make sense

**Deliverable**: Base distribution calculator working

---

### Step 5.2: Implement Mean Adjustment (Contextual Factors)
**Time**: 6-8 hours

**Tasks**:
- [ ] Implement minutes factor adjustment
- [ ] Implement pace factor adjustment
- [ ] Implement defense factor (opponent vs position)
- [ ] Implement usage factor (injury redistribution)
- [ ] Implement home/away factor
- [ ] Add clamping logic (0.85-1.20 for most factors)
- [ ] Test adjustments on various scenarios
- [ ] Verify adjusted means are reasonable

**Deliverable**: Mean adjustment working

---

### Step 5.3: Implement Variance Adjustment (Volatility)
**Time**: 6-8 hours

**Tasks**:
- [ ] Implement minutes volatility multiplier:
  - Locked starter: 0.90
  - Normal starter: 1.00
  - Bench/unstable: 1.20
- [ ] Implement usage volatility multiplier:
  - Stable usage: 0.90
  - Depends on others: 1.25
- [ ] Implement blowout risk multiplier
- [ ] Add variance clamping (0.8× to 1.5× base σ)
- [ ] Test variance adjustments
- [ ] Verify adjusted distributions

**Deliverable**: Variance adjustment working

---

### Step 5.4: Reconstruct Adjusted Distribution
**Time**: 4-6 hours

**Tasks**:
- [ ] Use scipy.stats.norm to create adjusted distribution
- [ ] Recalculate all percentiles from adjusted distribution
- [ ] Store distribution parameters (mean, std_dev, percentiles)
- [ ] Test distribution reconstruction
- [ ] Verify percentiles are consistent

**Deliverable**: Adjusted distribution reconstruction working

---

### Step 5.5: Implement Safe/Standard/Long Shot Definitions
**Time**: 4-6 hours

**Tasks**:
- [ ] Calculate safe bet line (25th percentile)
- [ ] Calculate safe bet probability (~75%)
- [ ] Calculate standard bet line (50th percentile/median)
- [ ] Calculate standard bet probability (~50%)
- [ ] Calculate long shot line (85th percentile)
- [ ] Calculate long shot probability (~15%)
- [ ] Test on various players
- [ ] Verify probabilities are reasonable

**Deliverable**: Bet type definitions working

---

### Step 5.6: Implement Pass Rules
**Time**: 4-6 hours

**Tasks**:
- [ ] Implement sample size check (<15 games → pass)
- [ ] Implement minutes check (<20 minutes → pass)
- [ ] Implement usage change check (>25% change → pass)
- [ ] Implement injury uncertainty check
- [ ] Implement volatility check (CV >40% → pass)
- [ ] Create pass reason tracking
- [ ] Test pass rules on edge cases
- [ ] Verify system correctly passes when needed

**Deliverable**: Pass rules working

---

### Step 5.7: Implement Minutes & Usage Redistribution
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `backend/app/services/redistribution_engine.py`
- [ ] Implement historical pattern learning:
  - Analyze games where starters were out
  - Calculate minutes increases for backups
  - Calculate usage redistribution
- [ ] Implement redistribution rules:
  - Minutes: +5-10 for primary backup
  - Usage: 60-70% to primary backup
- [ ] Calculate confidence scores based on sample size
- [ ] Integrate with distribution engine
- [ ] Test on historical injury scenarios
- [ ] Verify redistributions are reasonable

**Deliverable**: Redistribution engine working

---

### Step 5.8: Create Game Context Calculator
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `backend/app/services/game_context_calculator.py`:
  - Calculate rest days for each team
  - Calculate travel distance/time zone changes
  - Calculate blowout risk (based on point spread)
  - Store in database (add to games table or game_context table)
- [ ] Add rest day adjustments to prediction algorithm:
  - 0 rest days (back-to-back): -5% to stats
  - 1 rest day: baseline
  - 2+ rest days: +2% to stats
- [ ] Test context calculations
- [ ] Integrate with prediction engine

**Deliverable**: Game context calculator working

---

### Step 5.9: Create Prediction Service
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `backend/app/services/prediction_service.py`:
  - Function to generate distributions for all players in upcoming games
  - Function to recalculate after lineups confirmed
  - Function to get predictions for specific game
  - Function to get predictions for specific player
  - Function to refresh predictions
  - Function to check lineup status before generating
- [ ] Integrate all components:
  - Base distribution
  - Mean adjustment
  - Variance adjustment
  - Redistribution (if injuries)
  - Game context adjustments (rest days, travel)
  - Safe/Standard/Long Shot definitions
  - Pass rules
- [ ] Store full distribution data in `predictions` table
- [ ] Add lineup status to predictions (confirmed/pending)
- [ ] Test full prediction generation
- [ ] Optimize performance if needed

**Deliverable**: Complete prediction service working

---

### Step 5.10: Create Backtesting Framework
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `scripts/backtest_predictions.py`:
  - Run predictions on historical games (previous season)
  - Compare predictions to actual results
  - Calculate accuracy metrics:
    - Safe bet hit rate (target: 70-75%)
    - Long shot hit rate (target: 15-20%)
    - Overall prediction accuracy
    - Mean absolute error
  - Store backtest results in database
- [ ] Create backtest results table
- [ ] Run initial backtest on previous season
- [ ] Analyze results and identify areas for improvement
- [ ] Document findings

**Deliverable**: Backtesting framework working

---

### Step 5.11: Add Betting Line Comparison (Optional/Advanced)
**Time**: 4-6 hours (if implementing)

**Tasks**:
- [ ] Research sportsbook line data sources
- [ ] Implement line fetching (scrape or API)
- [ ] Calculate probability of going over line
- [ ] Convert book odds to implied probability
- [ ] Calculate edge (your prob - book prob)
- [ ] Flag edges (≥5% edge)
- [ ] Test line comparison
- [ ] Integrate with prediction output

**Deliverable**: Betting line comparison working (if implemented)

---

**Phase 5 Checkpoint**:
- ✅ Distribution engine working (base distributions)
- ✅ Mean adjustments working (contextual factors)
- ✅ Variance adjustments working (volatility)
- ✅ Adjusted distributions reconstructed
- ✅ Safe/Standard/Long Shot definitions working
- ✅ Pass rules implemented
- ✅ Minutes/usage redistribution working
- ✅ Game context calculator working (rest days, travel, blowout risk)
- ✅ Full prediction service integrated
- ✅ All predictions stored with full distribution data
- ✅ Backtesting framework working

**Before moving to Phase 6**: 
- Run backtest on previous season
- Verify safe bets hit ~70-75% of the time
- Verify long shots hit ~15-20% of the time
- Verify pass rules prevent bad bets
- Review backtest results and tune algorithm if needed

---

## Phase 6: Backend API Development
**Duration**: 1 week  
**Goal**: Create REST API endpoints for frontend

### Step 6.1: Set Up API Structure
**Time**: 2-3 hours

**Tasks**:
- [ ] Create `backend/app/api/__init__.py`
- [ ] Create `backend/app/api/routes.py` or separate route files
- [ ] Set up CORS for frontend connection
- [ ] Create basic health check endpoint
- [ ] Test API responds

**Deliverable**: API structure set up

---

### Step 6.2: Create Game Endpoints
**Time**: 3-4 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/games` (list games by date)
- [ ] Create endpoint: `GET /api/games/{game_id}` (game details)
- [ ] Create endpoint: `GET /api/games/upcoming` (upcoming games)
- [ ] Test endpoints

**Deliverable**: Game endpoints working

---

### Step 6.3: Create Player Endpoints
**Time**: 2-3 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/players` (list players)
- [ ] Create endpoint: `GET /api/players/{player_id}` (player details)
- [ ] Create endpoint: `GET /api/players/{player_id}/stats` (player stats)
- [ ] Test endpoints

**Deliverable**: Player endpoints working

---

### Step 6.4: Create Prediction Endpoints
**Time**: 4-6 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/predictions/game/{game_id}` (predictions for game)
- [ ] Create endpoint: `GET /api/predictions/player/{player_id}/game/{game_id}` (specific prediction)
- [ ] Create endpoint: `GET /api/predictions/safe-bets` (all safe bets)
- [ ] Create endpoint: `GET /api/predictions/long-shots` (all long shots)
- [ ] Create endpoint: `POST /api/predictions/generate` (trigger prediction generation)
- [ ] Test endpoints

**Deliverable**: Prediction endpoints working

---

### Step 6.5: Create Play Endpoints
**Time**: 4-6 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/plays` (list all plays)
- [ ] Create endpoint: `POST /api/plays` (create new play)
- [ ] Create endpoint: `GET /api/plays/{play_id}` (play details)
- [ ] Create endpoint: `PUT /api/plays/{play_id}` (update play - mark hit/miss)
- [ ] Create endpoint: `DELETE /api/plays/{play_id}` (delete play)
- [ ] Create endpoint: `GET /api/plays/stats` (play performance stats)
- [ ] Test endpoints

**Deliverable**: Play endpoints working

---

### Step 6.6: Create Analytics Endpoints
**Time**: 3-4 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/analytics/team-defense/{team_id}` (team defense stats)
- [ ] Create endpoint: `GET /api/analytics/matchup/{player_id}/{team_id}` (matchup history)
- [ ] Create endpoint: `GET /api/analytics/injuries` (current injuries)
- [ ] Test endpoints

**Deliverable**: Analytics endpoints working

---

### Step 6.7: Create Export Endpoints
**Time**: 3-4 hours

**Tasks**:
- [ ] Create endpoint: `GET /api/export/picks/{date}` (export picks as CSV)
- [ ] Create endpoint: `GET /api/export/plays` (export saved plays as CSV)
- [ ] Create endpoint: `GET /api/export/predictions/{game_id}` (export game predictions)
- [ ] Add CSV formatting
- [ ] Test exports

**Deliverable**: Export functionality working

---

### Step 6.8: API Documentation & Testing
**Time**: 2-3 hours

**Tasks**:
- [ ] Set up FastAPI automatic docs (`/docs`)
- [ ] Test all endpoints
- [ ] Add error handling
- [ ] Add input validation
- [ ] Document any special requirements

**Deliverable**: API fully documented and tested

---

**Phase 6 Checkpoint**:
- ✅ All API endpoints created
- ✅ Frontend can connect to backend
- ✅ CORS configured
- ✅ API documentation available
- ✅ All endpoints tested

**Before moving to Phase 7**: Test that frontend can fetch data from all endpoints.

---

## Phase 7: Frontend Development
**Duration**: 2-3 weeks  
**Goal**: Build user interface

### Step 7.1: Set Up Frontend Services
**Time**: 3-4 hours

**Tasks**:
- [ ] Create `frontend/src/services/api.js` (or .ts):
  - Set up Axios instance
  - Create API functions for all endpoints
  - Handle errors
- [ ] Test API connection
- [ ] Create utility functions if needed

**Deliverable**: Frontend API service working

---

### Step 7.2: Create Main Layout & Navigation
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `frontend/src/components/Layout.jsx`
- [ ] Create navigation component
- [ ] Set up routing (React Router):
  - `/` - Dashboard
  - `/games` - Games list
  - `/games/:gameId` - Game detail
  - `/plays` - My Plays
  - `/players/:playerId` - Player detail
- [ ] Create basic styling
- [ ] Test navigation

**Deliverable**: Layout and navigation working

---

### Step 7.3: Create Dashboard Page
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `frontend/src/pages/Dashboard.jsx`
- [ ] Display today's games
- [ ] Show game cards with quick stats
- [ ] Add date picker
- [ ] Display quick stats (total picks, injuries, etc.)
- [ ] Style dashboard
- [ ] Test functionality

**Deliverable**: Dashboard page working

---

### Step 7.4: Create Game List Page
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `frontend/src/pages/GamesList.jsx`
- [ ] Display list of games for selected date
- [ ] Show game info (teams, time, status)
- [ ] Show pick counts (safe bets, long shots)
- [ ] Add filters
- [ ] Add links to game detail page
- [ ] Style page

**Deliverable**: Game list page working

---

### Step 7.5: Create Game Detail Page
**Time**: 8-10 hours

**Tasks**:
- [ ] Create `frontend/src/pages/GameDetail.jsx`
- [ ] Display game information
- [ ] Display safe picks section:
  - List all safe picks
  - Show player, stat, range, likelihood
  - Add "Create Play" button
  - Add "View Details" link
- [ ] Display long shots section:
  - List all long shots
  - Show player, stat, range, likelihood, upside
  - Add "Create Play" button
- [ ] Display injury report
- [ ] Style page
- [ ] Test functionality

**Deliverable**: Game detail page working

---

### Step 7.6: Create Pick Detail Component/Page
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `frontend/src/components/PickDetail.jsx` or page
- [ ] Display full prediction details:
  - Player info
  - Prediction range and likelihood
  - Key factors
  - Matchup analysis
  - Recent form chart
  - Historical performance vs. opponent
- [ ] Add "Create Play" button
- [ ] Style component
- [ ] Test functionality

**Deliverable**: Pick detail view working

---

### Step 7.7: Create Play Creation Modal/Form
**Time**: 6-8 hours

**Tasks**:
- [ ] Create `frontend/src/components/CreatePlayModal.jsx`
- [ ] Form fields:
  - Player (pre-filled)
  - Game (pre-filled)
  - Stat type (pre-filled)
  - Bet line (user input, e.g., "Over 24.5")
  - Notes (optional)
- [ ] Add form validation
- [ ] Submit to API
- [ ] Handle success/error
- [ ] Close modal and refresh
- [ ] Style modal

**Deliverable**: Play creation working

---

### Step 7.8: Create My Plays Page
**Time**: 8-10 hours

**Tasks**:
- [ ] Create `frontend/src/pages/MyPlays.jsx`
- [ ] Display all saved plays
- [ ] Add filters (status, date, stat type)
- [ ] Add sorting options
- [ ] For each play, show:
  - Player, game, stat type
  - Bet line
  - Predicted range and likelihood
  - Status (Pending/Hit/Miss)
  - Actual result (if available)
  - Notes
- [ ] Add actions:
  - Mark as Hit
  - Mark as Miss
  - Edit (if pending)
  - Delete
- [ ] Display performance summary:
  - Total plays
  - Win rate
  - Recent trends
- [ ] Style page
- [ ] Test functionality

**Deliverable**: My Plays page working

---

### Step 7.9: Create Player Detail Page (Optional)
**Time**: 4-6 hours

**Tasks**:
- [ ] Create `frontend/src/pages/PlayerDetail.jsx`
- [ ] Display player information
- [ ] Display season statistics
- [ ] Display recent form chart
- [ ] Display upcoming games with predictions
- [ ] Style page

**Deliverable**: Player detail page working (if implementing)

---

### Step 7.10: Add Data Visualizations
**Time**: 4-6 hours

**Tasks**:
- [ ] Install chart library (Recharts or Chart.js)
- [ ] Create recent form chart component
- [ ] Create performance trend charts
- [ ] Add charts to relevant pages
- [ ] Style charts

**Deliverable**: Data visualizations working

---

### Step 7.11: Polish UI/UX
**Time**: 4-6 hours

**Tasks**:
- [ ] Improve styling and design
- [ ] Add loading states
- [ ] Add error handling and messages
- [ ] Add empty states
- [ ] Improve mobile responsiveness
- [ ] Test user flows
- [ ] Fix any bugs

**Deliverable**: Polished UI ready

---

**Phase 7 Checkpoint**:
- ✅ All pages created
- ✅ Navigation working
- ✅ Can view games and picks
- ✅ Can create plays
- ✅ Can track plays
- ✅ UI is functional and styled
- ✅ All user flows working

**Before moving to Phase 8**: Test complete user workflow end-to-end.

---

## Phase 8: Integration, Testing & Refinement
**Duration**: 1 week  
**Goal**: Integrate everything, test, and refine

### Step 8.1: End-to-End Testing
**Time**: 4-6 hours

**Tasks**:
- [ ] Test complete user workflow:
  - View games
  - View picks
  - Create play
  - Track play outcome
- [ ] Test data flow:
  - Data collection → Analytics → Predictions → Display
- [ ] Test edge cases:
  - Missing data
  - No predictions available
  - Invalid inputs
- [ ] Fix any bugs found

**Deliverable**: System tested end-to-end

---

### Step 8.2: Data Quality Validation
**Time**: 3-4 hours

**Tasks**:
- [ ] Run data validation scripts
- [ ] Check prediction accuracy on past games
- [ ] Verify analytics calculations
- [ ] Fix any data issues
- [ ] Document any known limitations

**Deliverable**: Data quality validated

---

### Step 8.3: Performance Optimization
**Time**: 4-6 hours

**Tasks**:
- [ ] Review database schema and add indexes:
  - Index on player_id, game_id in player_game_stats
  - Index on team_id, position in team_position_defense
  - Index on game_date in games
  - Index on player_id, opponent_team_id in player_team_matchups
- [ ] Optimize slow queries (use EXPLAIN ANALYZE)
- [ ] Add caching for frequently accessed data:
  - Team defense stats
  - Recent player form
  - Current injury status
- [ ] Optimize API endpoints (response time targets: <500ms)
- [ ] Optimize frontend rendering (lazy loading, pagination)
- [ ] Test with larger datasets
- [ ] Monitor query performance

**Deliverable**: Performance optimized with indexes and caching

---

### Step 8.4: Documentation
**Time**: 4-6 hours

**Tasks**:
- [ ] Update README with setup instructions
- [ ] Document how to run daily updates
- [ ] Document how to use the system
- [ ] Document any configuration needed
- [ ] Create troubleshooting guide

**Deliverable**: Documentation complete

---

### Step 8.5: Final Refinement
**Time**: 4-6 hours

**Tasks**:
- [ ] Review all features
- [ ] Fix any remaining bugs
- [ ] Improve error messages
- [ ] Add any missing features
- [ ] Final UI polish
- [ ] User acceptance testing

**Deliverable**: System ready for use

---

**Phase 8 Checkpoint**:
- ✅ All features working
- ✅ System tested
- ✅ Performance acceptable
- ✅ Documentation complete
- ✅ Ready for daily use

---

## Post-Launch: Maintenance & Improvements

### Data Updates: Automatic vs Manual

**What Updates Automatically** (once set up):
- ✅ **Daily game results** - Previous day's games scraped automatically (if cron/schedule set up)
- ✅ **Player statistics** - Updated from new game results
- ✅ **Game schedules** - Upcoming games updated
- ✅ **Analytics recalculations** - Team defense, matchups recalculated after new data

**What Needs Manual Intervention**:
- ⚠️ **Injury updates** - Can be automated but may need verification (especially on game days)
- ⚠️ **Initial historical data** - Previous season scraped once manually
- ⚠️ **Prediction recalculation** - Runs automatically after data updates, but you may want to trigger manually before games

**Update Schedule** (if automated):
- **Daily at 6 AM**: Previous day's game results
- **Every 2 hours on game days**: Injury updates (optional, can be manual)
- **Daily at 8 AM**: Upcoming game schedules
- **After data updates**: Analytics and predictions recalculate automatically

**Manual Alternative**:
If you don't set up automation, you can run:
```bash
# Daily update (run once per day)
python scripts/daily_update.py

# Before games (60-120 min before tipoff)
python scripts/refresh_predictions.py  # Recalculate with confirmed lineups
```

**First-Time Setup**:
- Initial scrape of previous season: **One-time manual run**
- Current season data: **Ongoing automatic** (or manual daily)

### Ongoing Tasks:
- [ ] Run daily data updates (or verify automation is working)
- [ ] Monitor data quality
- [ ] Track prediction accuracy
- [ ] Update injury data regularly (or verify automated updates)
- [ ] Refine prediction algorithm based on results
- [ ] Add new features as needed

### Potential Future Enhancements:
- [ ] Machine learning models
- [ ] Real-time game tracking
- [ ] Historical bet tracking with ROI
- [ ] Custom alerts
- [ ] Comparison tools
- [ ] Export functionality

---

## Quick Reference: Build Order Summary

1. **Phase 1**: Project setup, database, models (3-5 days)
2. **Phase 2**: Data collection infrastructure (1-2 weeks)
3. **Phase 3**: Analytics engine (1-2 weeks)
4. **Phase 4**: Injury tracking (1 week)
5. **Phase 5**: Prediction engine (1-2 weeks)
6. **Phase 6**: Backend API (1 week)
7. **Phase 7**: Frontend development (2-3 weeks)
8. **Phase 8**: Integration & testing (1 week)

**Total Estimated Time**: 8-12 weeks

---

## Tips for Success

1. **Complete each phase fully** before moving to the next
2. **Test frequently** - don't wait until the end
3. **Commit code regularly** - use Git for version control
4. **Document as you go** - it's easier than documenting later
5. **Start simple** - get basic functionality working first, then enhance
6. **Validate data early** - bad data will break everything downstream
7. **Ask for help** - use Stack Overflow, documentation, etc.

---

*Document Version: 1.0*
*Last Updated: [Current Date]*

