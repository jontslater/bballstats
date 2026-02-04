# NBA Data Sources & Alternatives

## Current Data Source

**Primary:** `nba_api` Python package (unofficial wrapper around NBA.com endpoints)

**Status:** Working but has limitations:
- Some dates don't return box scores (especially recent games)
- Rate limiting issues
- May return empty responses

## Alternative Data Sources

### 1. Basketball Reference (basketball-reference.com) ⭐ RECOMMENDED
**Why:** Most comprehensive, reliable, industry standard

**What it provides:**
- Complete game logs (current + historical seasons)
- Player box scores
- Team statistics
- Advanced metrics
- Schedule information

**Implementation:**
- Scrape with BeautifulSoup or Scrapy
- Respect rate limits (2-3 seconds between requests)
- More reliable than NBA API for historical data

**Pros:**
- ✅ Most comprehensive data
- ✅ Historical data available
- ✅ Well-structured HTML
- ✅ Industry standard

**Cons:**
- ⚠️ Requires scraping (more complex)
- ⚠️ Rate limiting needed
- ⚠️ HTML structure may change

### 2. ESPN API (if available)
**Status:** ESPN doesn't have a public API, but we could scrape ESPN.com

**What it provides:**
- Game results
- Player stats
- Injury reports
- Lineup confirmations

### 3. Stats.NBA.com (Official NBA Stats)
**Status:** Official NBA stats site, but requires scraping

**What it provides:**
- Official game data
- Player statistics
- Team statistics

### 4. Keep Using nba_api but Add Fallbacks
**Current approach with improvements:**
- Use `nba_api` as primary
- Add Basketball Reference scraper as fallback
- Cache results to reduce API calls

## Recommended Solution

**Hybrid Approach:**
1. **Primary:** Continue using `nba_api` for real-time data
2. **Fallback:** Add Basketball Reference scraper for:
   - Historical data collection
   - When NBA API fails
   - Verification of data

**Implementation Priority:**
1. ✅ Keep current `nba_api` implementation
2. 🔄 Add Basketball Reference scraper for historical games
3. 🔄 Add retry logic with fallback to Basketball Reference
4. 🔄 Cache results to reduce API calls

## Why "Pass" Predictions Show Up

**"Pass" predictions** are predictions where the system determined the bet was too risky or uncertain. These are:
- Filtered out from recommended bets
- Still stored in database for analysis
- Excluded from historical results by default (now fixed)

**"Processing"** likely refers to games that haven't finished yet or predictions that haven't been evaluated.

## Current Status

- ✅ Backend filters out "pass" predictions from historical results
- ✅ Frontend groups results by game
- ✅ Added explanation of ± notation
- ✅ Shows predicted vs actual comparison with difference
- ⚠️ Some games missing stats (NBA API issue)

## Next Steps

1. **Add Basketball Reference scraper** for historical data
2. **Improve game stats collection** with fallback sources
3. **Add caching** to reduce API calls
4. **Better error handling** when data unavailable





