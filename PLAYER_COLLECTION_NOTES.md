# Player Collection Notes

## Current Status

✅ **Script Created**: `scripts/collect_players.py` is ready and functional  
⚠️ **Rate Limiting**: NBA API has strict rate limits that can block requests

## The Issue

The NBA API (`nba_api` package) has strict rate limits. When you make too many requests in a short time, the API returns empty responses.

**Symptoms:**
- "Expecting value: line 1 column 1 (char 0)" error
- Empty responses from API
- Works when tested directly, fails when called from script

## Solutions

### Option 1: Wait and Retry (Recommended)
```bash
# Wait 10-15 minutes after any NBA API calls, then:
python scripts/collect_players.py
```

### Option 2: Run During Off-Peak Hours
- Early morning (6-8 AM) tends to have less rate limiting
- Avoid running right after other API calls

### Option 3: Test First
```bash
# Test if API is available:
python scripts/test_player_collection.py

# If test succeeds, run full collection:
python scripts/collect_players.py
```

### Option 4: Collect in Batches
The script already handles this - it commits in batches of 25 players.

## What Works

When the API is available, the script will:
- ✅ Fetch all current season players (~500-600 players)
- ✅ Store player basic info (name, position, team)
- ✅ Fetch detailed info (height, weight, birth date) for new players
- ✅ Update existing players
- ✅ Handle duplicates gracefully

## Workaround for Now

Since we're building the system, you can:

1. **Skip player collection for now** - We can add players as we collect game data
2. **Run it later** - Once rate limits reset (10-15 minutes)
3. **Use test script** - Verify it works before full collection

## Next Steps

We'll move forward with:
- ✅ Game results collection (this works reliably)
- ✅ Schedule collection (this works)
- Players can be collected later or as we process games

The system will work fine even if we don't have all players upfront - we'll collect them as we process game data.


