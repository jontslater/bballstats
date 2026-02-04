# Suggested Bets and Parlays Feature

## Overview
Added a comprehensive suggested bets and parlays system that recommends the best betting opportunities based on prediction quality, confidence, and probability.

## Why No Bets Are Showing

**You need to generate predictions first!** The suggested bets feature requires predictions to exist. 

To generate predictions:
1. Click the "Generate Predictions" button on the Dashboard
2. Wait for the progress bar to complete
3. Suggested bets and parlays will appear automatically

## Features

### 1. Suggested Bets
**Backend**: `backend/app/services/suggested_bets.py`
**API**: `GET /api/suggested-bets/bets`

- Ranks predictions by quality score
- Quality score considers:
  - Probability (higher = better)
  - Confidence level (HIGH/MEDIUM/LOW)
  - Volatility (LOW volatility = better)
- Filters to only show HIGH/MEDIUM confidence predictions
- Minimum probability threshold for safe bets (default: 65%)

**Scoring Formula**:
```
Score = (Probability × Weight) + Confidence Bonus + Volatility Bonus
- Safe bets: Probability × 100
- Standard bets: Probability × 80
- Long shots: Probability × 60
- HIGH confidence: +30 points
- MEDIUM confidence: +15 points
- LOW volatility: +20 points
- MEDIUM volatility: +10 points
```

### 2. Suggested Parlays
**API**: `GET /api/suggested-bets/parlays`

Two modes:
1. **Stat Mix Mode** (default): Creates parlays with mix of points, rebounds, and assists
   - 3-leg parlays: One of each stat type
   - 2-leg parlays: Different stat types
   - Ensures different players (diversification)

2. **General Mode**: Creates parlays from top suggested bets
   - 2-4 leg parlays
   - Ensures different players
   - Calculates combined odds and probability

**Parlay Features**:
- Combines probabilities (multiplies them)
- Converts to American odds format
- Shows combined probability percentage
- Displays each leg with player, stat, line, and probability

## Frontend Display

### Suggested Bets Section
- Shows top 10 suggested bets
- Displays:
  - Player name and team
  - Stat type (points/rebounds/assists)
  - Bet type badge (safe/standard/long_shot)
  - Line (e.g., "PTS Over 24.5")
  - Probability percentage
  - Confidence and volatility levels

### Suggested Parlays Section
- Shows top 5 suggested parlays
- Displays:
  - Number of legs
  - Combined probability
  - Combined odds (American format, e.g., "+450")
  - Each leg with player, stat, line, and probability

## API Endpoints

### Get Suggested Bets
```
GET /api/suggested-bets/bets?game_date=2025-12-28&limit=10
```

### Get Suggested Parlays
```
GET /api/suggested-bets/parlays?game_date=2025-12-28&limit=5&mix_stats=true
```

## Usage

1. **Generate Predictions**: Click "Generate Predictions" button
2. **View Suggestions**: Suggested bets and parlays appear automatically
3. **Create Plays**: Click on a suggested bet to create a play
4. **Build Parlays**: Use suggested parlays or create your own from suggested bets

## Next Steps

To see suggested bets:
1. Make sure you have games for today
2. Click "Generate Predictions" 
3. Wait for generation to complete
4. Suggested bets and parlays will appear on the dashboard

The system will automatically rank and suggest the best betting opportunities based on:
- High probability of success
- Strong confidence levels
- Low volatility
- Good sample sizes





