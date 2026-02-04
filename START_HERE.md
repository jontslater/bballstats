# 🏀 Start Here - Quick Setup

## What We Just Created

✅ **Project structure** - All directories created  
✅ **FastAPI backend** - Basic app ready  
✅ **Database connection** - Configured and ready  
✅ **Virtual environment** - Set up with dependencies  

## Next Steps

### 1. Set Up Database (2 minutes)

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE nba_betting;

# Exit
\q
```

### 2. Configure Database Connection

Edit `backend/.env` file:
```bash
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/nba_betting
```

### 3. Test the Backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

Visit: http://localhost:8000  
API Docs: http://localhost:8000/docs

### 4. Test Database Connection

Visit: http://localhost:8000/health

Should show: `{"status": "healthy", "database": "connected"}`

---

## What's Working Now

- ✅ FastAPI server runs
- ✅ Health check endpoint works
- ✅ Database connection configured
- ✅ CORS configured for frontend
- ✅ Project structure ready

## What's Next (Following Execution Plan)

1. **Create database models** (Phase 1, Step 1.5)
   - Player, Team, Game, etc.
   
2. **Create database tables** (Phase 1, Step 1.5)
   - Run migrations to create tables
   
3. **Seed basic data** (Phase 1, Step 1.6)
   - Teams, seasons
   
4. **Start data collection** (Phase 2)
   - NBA API integration
   - Scraping setup

---

## Quick Commands

```bash
# Start backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# Test database connection
python -c "from app.database import engine; engine.connect(); print('✅ Connected!')"

# Check health
curl http://localhost:8000/health
```

---

**Ready to continue?** Follow EXECUTION_PLAN.md Phase 1, Step 1.5 to create database models!





