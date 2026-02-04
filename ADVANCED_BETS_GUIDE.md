# Advanced Bets Guide

## 🎯 New Bet Types Available

The system now generates **6 additional bet types** beyond basic Over/Under props:

---

## 1. **Combo Props** 🎯

**What it is:** Combined stat bets (e.g., Points + Rebounds Over 30.5)

**Types:**
- Points + Rebounds
- Points + Assists  
- Rebounds + Assists

**How it works:**
- Combines two stat predictions using probability distributions
- Calculates combined mean and variance
- Generates safe/standard/long shot lines for the combo

**Example:**
```
LeBron James: Points + Rebounds Over 32.5
Probability: 72%
Bet Type: Safe
```

**API:**
```
GET /api/advanced-bets/combo-props/{game_id}/{player_id}?combo_type=points_rebounds
```

---

## 2. **Milestone Props** 🏆

**What it is:** Milestone achievement bets (e.g., 20+ points, double-double, triple-double)

**Types:**
- Points milestones: 15+, 20+, 25+, 30+, 35+
- Rebounds milestones: 5+, 10+, 15+, 20+
- Assists milestones: 5+, 10+, 15+
- Double-double (10+ points & 10+ rebounds)
- Triple-double (10+ points, 10+ rebounds, 10+ assists)

**How it works:**
- Uses distribution to calculate probability of hitting each milestone
- For double/triple-doubles, calculates joint probability

**Example:**
```
LeBron James: 25+ Points
Probability: 45%
Bet Type: Milestone
```

**API:**
```
GET /api/advanced-bets/milestone-props/{game_id}/{player_id}
```

---

## 3. **Player vs Player Props** ⚔️

**What it is:** Head-to-head comparisons (e.g., LeBron points vs Curry points)

**How it works:**
- Compares two players' predictions for the same stat
- Calculates difference distribution
- Provides win probability and margin probabilities

**Example:**
```
LeBron James vs Stephen Curry (Points)
Expected Difference: +3.2
LeBron Win Probability: 62%
LeBron Win by 5+: 28%
```

**API:**
```
GET /api/advanced-bets/player-vs-player/{game_id}/{player1_id}/{player2_id}?stat_type=points
```

---

## 4. **Alternate Lines** 📈

**What it is:** Multiple line options for the same stat (e.g., Over 20.5, 22.5, 24.5, 26.5)

**How it works:**
- Generates lines at different percentiles (10th, 20th, 25th, 30th, etc.)
- Provides probability and estimated odds for each line
- Allows finding the best value line

**Example:**
```
LeBron James Points:
- Over 20.5: 85% probability (-567)
- Over 22.5: 72% probability (-257)
- Over 24.5: 58% probability (-138)
- Over 26.5: 42% probability (+138)
```

**API:**
```
GET /api/advanced-bets/alternate-lines/{game_id}/{player_id}/{stat_type}
```

---

## 5. **Performance Brackets** 📊

**What it is:** Range-based bets (e.g., 15-20 points, 20-25 points)

**How it works:**
- Calculates probability of player landing in specific ranges
- Provides multiple bracket options
- Useful for finding value in specific ranges

**Example:**
```
LeBron James Points:
- 20-25 Points: 35% probability
- 25-30 Points: 28% probability
- 15-20 Points: 22% probability
```

**API:**
```
GET /api/advanced-bets/performance-brackets/{game_id}/{player_id}/{stat_type}
```

---

## 6. **Team Totals** 📊

**What it is:** Team total props (e.g., Lakers Total Points Over 115.5)

**How it works:**
- Sums all player predictions for a team
- Generates team total distribution
- Provides multiple line options with probabilities

**Example:**
```
Lakers Total Points:
Expected: 112.3
- Over 110: 58% probability (-138)
- Over 115: 42% probability (+138)
- Over 120: 28% probability (+257)
```

**API:**
```
GET /api/advanced-bets/team-totals/{game_id}/{team_id}?stat_type=points
```

---

## 🎮 How to Use

### **Get All Advanced Bets for a Game:**
```
GET /api/advanced-bets/game/{game_id}?limit_per_type=5
```

**Returns:**
```json
{
  "combo_props": [...],
  "milestone_props": [...],
  "player_vs_player": [...],
  "alternate_lines": [...],
  "performance_brackets": [...],
  "team_totals": [...]
}
```

### **Frontend Integration:**
The Game Detail page now has a "Show Advanced Bets" button that displays:
- Combo Props
- Milestone Props
- Player vs Player
- Team Totals
- Alternate Lines (info)
- Performance Brackets (info)

---

## 💡 Use Cases

### **1. Finding Value:**
- Use alternate lines to find the best line for your risk tolerance
- Compare combo props to individual stat lines
- Use team totals to find team-based value

### **2. Diversification:**
- Mix individual props with combo props
- Add milestone props for higher odds
- Use player vs player for head-to-head excitement

### **3. Risk Management:**
- Use performance brackets for range-based betting
- Use alternate lines to adjust risk/reward
- Use team totals for lower variance bets

---

## 📊 Expected Value

### **Combo Props:**
- Often have better odds than individual props
- Good for players who consistently hit both stats
- Example: Points + Rebounds combo often pays better than separate bets

### **Milestone Props:**
- Higher odds for milestone achievements
- Good for players trending toward milestones
- Example: 25+ points pays better than Over 24.5

### **Player vs Player:**
- Great for head-to-head matchups
- Often have competitive odds
- Example: Star player vs star player comparisons

### **Team Totals:**
- Lower variance than individual props
- Good for game flow analysis
- Example: High pace game = higher team totals

---

## ✅ Benefits

1. **More Betting Options** - 6 new bet types = more opportunities
2. **Better Value Finding** - Alternate lines help find best odds
3. **Diversification** - Mix different bet types for portfolio
4. **Risk Management** - Brackets and team totals offer lower variance
5. **Excitement** - Player vs player and milestones add fun

---

## 🚀 Next Steps

These advanced bets are now available via API and will appear on the Game Detail page when you click "Show Advanced Bets". All bets use the same comprehensive 30+ factor prediction system, ensuring accuracy and value identification.





