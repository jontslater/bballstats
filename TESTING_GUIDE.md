# Testing Guide

## What We've Built So Far

### ✅ Phase 1 Complete:
1. **Project Structure** - All directories created
2. **FastAPI Backend** - Basic app running
3. **Database Models** - All 13 models created
4. **Seeding Scripts** - Teams and seasons ready
5. **Test Scripts** - Database testing ready

## Testing Checklist

### 1. Test Database Connection
```bash
python scripts/test_database.py
```

**Expected Output:**
- ✅ Database connection successful
- ✅ All 13 tables created
- ✅ Table structures verified
- ✅ Relationships working

### 2. Seed Initial Data
```bash
# Seed teams
python scripts/seed_teams.py

# Seed seasons  
python scripts/seed_seasons.py
```

**Expected Output:**
- ✅ 30 teams seeded
- ✅ 2 seasons seeded (current + previous)

### 3. Test FastAPI Server
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**Test endpoints:**
- http://localhost:8000 - Root endpoint
- http://localhost:8000/health - Health check
- http://localhost:8000/docs - API documentation

### 4. Verify Database Content
```bash
psql -U postgres -d nba_betting

# Check teams
SELECT COUNT(*) FROM teams;  -- Should be 30

# Check seasons
SELECT * FROM seasons;  -- Should show 2 seasons

# Check tables
\dt  -- Should list all 13 tables
```

## What to Test

### Database Tests
- [ ] Connection works
- [ ] All tables created
- [ ] Table structures correct
- [ ] Relationships work
- [ ] Can insert data (teams/seasons)
- [ ] Can query data

### API Tests
- [ ] Server starts
- [ ] Health endpoint works
- [ ] Database connection in health check
- [ ] CORS configured
- [ ] API docs accessible

### Model Tests
- [ ] All models import
- [ ] Relationships configured
- [ ] Foreign keys work
- [ ] Unique constraints work

## Common Issues

### Import Errors
- Make sure you're in the project root
- Virtual environment activated
- Python path includes backend directory

### Database Errors
- Check PostgreSQL is running
- Verify DATABASE_URL in .env
- Ensure database exists
- Check user permissions

### Table Creation Errors
- Check database connection first
- Verify all models import correctly
- Check for syntax errors in models

## Next: Phase 2 Testing

Once Phase 1 is fully tested, we'll test:
- NBA API integration
- Data collection scripts
- Data validation

---

**Remember:** Test as you build! Don't move forward until current phase is fully tested.


