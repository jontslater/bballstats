# Bankroll Recommendation System - Planning Document

## Overview
A system that takes user's bankroll and recommends optimal betting strategies and specific plays.

## User Inputs
1. **Total Bankroll**: Amount of money available (e.g., $50)
2. **Reserve Amount**: Amount to save/reserve (e.g., $20)
3. **Available to Bet**: Calculated automatically (Total - Reserve, e.g., $30)

## Recommendation Strategies

### 1. Poor Man's Bet Challenge
- **Best for**: Small bankrolls ($1-$5), aggressive growth goals
- **Risk**: High (compound daily, no failure tolerance)
- **Time**: 14 days to reach ~$1000
- **When to suggest**: 
  - User has small amount available ($1-$10)
  - Wants aggressive growth
  - Has 14+ days to commit

### 2. Builder Plays
- **Best for**: Moderate bankrolls ($10-$100), steady growth
- **Risk**: Medium (2-3 leg parlays, ~80% combined probability)
- **Time**: Resolves same day
- **Return**: ~2x multiplier
- **When to suggest**:
  - User has moderate amount ($10-$100)
  - Wants steady, safe growth
  - Prefers daily resolution

### 3. Safe Long Parlays
- **Best for**: Larger bankrolls ($50+), lottery-style bets
- **Risk**: Low per leg but high overall (10-15 legs)
- **Time**: Resolves same day
- **Return**: High multiplier (20x-100x+)
- **When to suggest**:
  - User has larger amount ($50+)
  - Wants to risk small portion on long shot
  - Can afford to lose the bet

### 4. Individual Safe Bets
- **Best for**: Any bankroll size, capital preservation
- **Risk**: Low (75%+ probability)
- **Time**: Resolves same day
- **Return**: ~1.3x multiplier
- **When to suggest**:
  - User wants to preserve capital
  - Conservative approach
  - Diversification

### 5. Mixed Strategy
- **Best for**: Larger bankrolls, balanced approach
- **Allocation**:
  - 60% on Builder Plays (safe growth)
  - 30% on Safe Long Parlays (lottery shot)
  - 10% on Individual Safe Bets (hedge)

## Recommendation Logic

### Priority Factors:
1. **Bankroll Size**
   - < $10: Suggest Poor Man's Bet
   - $10-$50: Builder Plays or mix
   - $50+: Mixed strategy or Safe Long Parlays

2. **Goals** (if we can infer or user provides)
   - Growth: Poor Man's Bet or Builder Plays
   - Preservation: Individual Safe Bets
   - Lottery: Safe Long Parlays

3. **Risk Tolerance** (if user provides)
   - Conservative: Individual Safe Bets
   - Moderate: Builder Plays
   - Aggressive: Poor Man's Bet or Safe Long Parlays

## Money Allocation Strategy

### For Single Strategy:
- Allocate all available amount based on strategy's bet sizing

### For Mixed Strategy:
- Calculate optimal allocation based on:
  - Strategy risk/return profiles
  - Available amount
  - Minimum bet requirements

## Database Models

### UserBankroll
- `bankroll_id`: Primary key
- `user_id`: (if multi-user in future)
- `total_bankroll`: DECIMAL(10, 2)
- `reserve_amount`: DECIMAL(10, 2)
- `available_to_bet`: DECIMAL(10, 2) - calculated
- `last_updated`: DateTime

### BankrollRecommendation
- `recommendation_id`: Primary key
- `bankroll_id`: Foreign key
- `recommended_date`: Date
- `strategy_type`: String (poor_mans_bet, builder, long_parlay, safe_bets, mixed)
- `recommended_allocation`: JSON/Text (details of allocation)
- `reasoning`: Text
- `status`: String (pending, accepted, rejected)

## API Endpoints

### POST /api/bankroll/recommendations
**Request:**
```json
{
  "total_bankroll": 50.00,
  "reserve_amount": 20.00,
  "game_date": "2024-01-15",  // optional, defaults to today
  "risk_tolerance": "moderate"  // optional: conservative, moderate, aggressive
}
```

**Response:**
```json
{
  "available_to_bet": 30.00,
  "recommendations": [
    {
      "strategy": "builder",
      "priority": 1,
      "allocation": 30.00,
      "reasoning": "Your $30 bankroll is perfect for builder plays. Suggested 2-3 leg parlays with 80%+ combined probability.",
      "suggested_bets": [
        {
          "bet_type": "builder_play",
          "amount": 10.00,
          "parlay_legs": [...],
          "expected_return": 18.00,
          "probability": 0.75
        },
        {
          "bet_type": "builder_play",
          "amount": 10.00,
          "parlay_legs": [...],
          "expected_return": 19.00,
          "probability": 0.78
        },
        {
          "bet_type": "builder_play",
          "amount": 10.00,
          "parlay_legs": [...],
          "expected_return": 17.50,
          "probability": 0.72
        }
      ]
    },
    {
      "strategy": "poor_mans_bet",
      "priority": 2,
      "allocation": 5.00,
      "reasoning": "Start a Poor Man's Bet challenge with $5. Can grow to $1000 in 14 days if successful.",
      "challenge_config": {
        "start_amount": 5.00,
        "target_amount": 1000.00,
        "days_target": 14
      }
    }
  ]
}
```

## Service Layer

### BankrollRecommendationService
Methods:
- `get_recommendations(total_bankroll, reserve_amount, game_date, risk_tolerance)`
- `_calculate_available_amount(total, reserve)`
- `_select_strategies(available_amount, risk_tolerance)`
- `_generate_builder_play_recommendations(amount, game_date)`
- `_generate_poor_mans_bet_recommendation(amount)`
- `_generate_safe_long_parlay_recommendations(amount, game_date)`
- `_generate_safe_bet_recommendations(amount, game_date)`
- `_generate_mixed_strategy_recommendations(amount, game_date)`
- `_allocate_money(strategies, total_amount)`

## Questions for User:

1. **Strategy Selection**: Should we always suggest multiple strategies ranked by priority, or just the best one?

2. **Allocation**: When suggesting multiple bets (e.g., 3 builder plays), should we:
   - Split equally?
   - Split by probability (higher probability = larger bet)?
   - Split by expected ROI?
   - Let user adjust after seeing recommendations?

3. **Integration**: Should this:
   - Create the bets automatically when user accepts?
   - Just provide recommendations and user places bets manually?
   - Create a "recommended portfolio" that user can review and approve?

4. **Persistence**: Should we:
   - Save recommendations for reference?
   - Track which recommendations were accepted/rejected?
   - Learn from user preferences over time?

5. **Risk Tolerance**: Should this be:
   - A user setting they configure once?
   - Asked each time?
   - Inferred from their betting history?




