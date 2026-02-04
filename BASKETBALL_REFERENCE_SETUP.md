# Basketball Reference Scraper Setup

## Overview

We've added a **Basketball Reference scraper** as a fallback data source when the NBA API fails or doesn't return box scores. This is especially useful for recent games where the NBA API may be unreliable.

## How It Works

1. **Primary Source**: NBA API (via `nba_api` package)
2. **Fallback Source**: Basketball Reference scraper
3. **Automatic Fallback**: When NBA API fails or returns no player stats, the system automatically tries Basketball Reference

## Implementation

### Files Created

- `backend/app/scrapers/basketball_reference.py` - Main scraper class
- Updated `scripts/collect_game_results.py` - Now uses Basketball Reference as fallback

### Features

- ✅ Scrapes box scores from basketball-reference.com
- ✅ Parses player stats (points, rebounds, assists, etc.)
- ✅ Handles team abbreviation differences
- ✅ Rate limiting (2 seconds between requests)
- ✅ Automatic fallback when NBA API fails
- ✅ Converts Basketball Reference format to NBA API format

## Usage

The scraper is **automatically used** when you run:

```bash
python scripts/collect_game_results.py --previous-day
```

Or for a specific date:

```bash
python scripts/collect_game_results.py --date 2024-12-28
```

## How It Handles Player Matching

Since Basketball Reference doesn't have NBA player IDs, the scraper matches players by:
1. **Exact name match** - Tries to find player in database by name
2. **Team context** - Uses team abbreviation to narrow down matches

**Note**: If a player isn't found in the database, that player's stats will be skipped (with a warning). This is expected for players who haven't been collected yet.

## Rate Limiting

Basketball Reference recommends 2-3 seconds between requests. The scraper enforces a 2-second delay by default.

## Testing

You can test the scraper directly:

```python
from backend.app.scrapers.basketball_reference import BasketballReferenceScraper
from datetime import date, timedelta

scraper = BasketballReferenceScraper()
yesterday = date.today() - timedelta(days=1)

# Get games for a date
games = scraper.get_games_for_date(yesterday)
print(f"Found {len(games)} games")

# Get box score for a specific game
if games:
    box_score = scraper.get_box_score(games[0]['box_score_url'], yesterday)
    print(f"Players: {len(box_score['player_stats'])}")
```

## Benefits

1. **More Reliable**: Basketball Reference is more reliable for recent games
2. **Complete Data**: Often has box scores when NBA API doesn't
3. **Historical Data**: Can be used for historical game collection
4. **Automatic**: No manual intervention needed - just works as fallback

## Limitations

- Requires players to already be in database (matched by name)
- Slower than NBA API (2 second delays)
- HTML structure could change (though it's been stable for years)
- No player IDs (must match by name)

## Next Steps

1. ✅ Scraper implemented
2. ✅ Integrated into game results collection
3. 🔄 Test with recent games
4. 🔄 Add fuzzy name matching for better player matching
5. 🔄 Consider caching to reduce requests





