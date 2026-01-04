# Frontend Troubleshooting Guide

## Current Status
✅ **61 upcoming games** in database  
✅ **344 predictions for today** (2025-12-28)  
✅ **6 games scheduled for today**

## Issue: Frontend Not Showing Data

### Possible Causes:

1. **API Not Running**
   - Check if backend is running: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload`
   - Check if frontend is running: `cd frontend && npm run dev`
   - Check API health: Open `http://localhost:8000/health` in browser

2. **CORS Issues**
   - Check browser console for CORS errors
   - Verify `VITE_API_URL` in frontend `.env` file

3. **Date Filter Issue**
   - Frontend defaults to today's date
   - Check if games exist for today: 6 games should be visible
   - Try changing the date picker to tomorrow (2025-12-29) to see 11 games

4. **API Timeout**
   - Prediction generation can take 2-5 minutes for 6 games
   - Button stays grayed out while generating
   - Check backend logs for progress

## Quick Tests

### Test 1: Check API Directly
```bash
# Test games endpoint
curl http://localhost:8000/api/games?game_date=2025-12-28

# Test predictions endpoint
curl http://localhost:8000/api/predictions/safe-bets?game_date=2025-12-28
```

### Test 2: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for:
   - API errors
   - Network errors
   - CORS errors
   - Failed requests

### Test 3: Check Network Tab
1. Open browser DevTools (F12)
2. Go to Network tab
3. Refresh page
4. Look for:
   - Failed requests (red)
   - Request URLs
   - Response status codes

## Fixes Applied

1. ✅ **Added timeout handling** - Frontend now has 5-minute timeout
2. ✅ **Limited to 1 day** - Backend now only generates for 1 day to avoid timeout
3. ✅ **Better error messages** - More detailed error reporting

## Manual Data Check

```bash
cd /Users/lisaannparr/bballstats
source backend/venv/bin/activate

# Check games
python -c "from app.database import SessionLocal; from app.models import Game; from datetime import date; db = SessionLocal(); print(f'Games today: {db.query(Game).filter(Game.game_date == date.today()).count()}')"

# Check predictions
python -c "from app.database import SessionLocal; from app.models import Prediction; db = SessionLocal(); print(f'Total predictions: {db.query(Prediction).count()}')"
```

## Next Steps

1. **Check if backend is running**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. **Check if frontend is running**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Check browser console** for errors

4. **Try the date picker** - Change to tomorrow to see if games appear

5. **Check API directly** - Use curl or browser to test endpoints


