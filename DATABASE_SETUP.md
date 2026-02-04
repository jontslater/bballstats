# Database Setup Guide

## Current Status

✅ **All scripts created and ready!**
- Database models: ✅ Created (13 models)
- Seeding scripts: ✅ Created (teams & seasons)
- Test script: ✅ Created and working

⚠️ **Database needs to be set up**

## Step 1: Install PostgreSQL (if not installed)

### Mac (using Homebrew):
```bash
brew install postgresql@14
brew services start postgresql@14
```

### Linux (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### Windows:
Download from: https://www.postgresql.org/download/windows/

## Step 2: Create Database

```bash
# Connect to PostgreSQL
psql postgres

# Create database
CREATE DATABASE nba_betting;

# Create user (optional - can use default)
CREATE USER nba_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE nba_betting TO nba_user;

# Exit
\q
```

## Step 3: Configure Connection

Create `backend/.env` file:

```bash
cd backend
cp .env.example .env  # if .env.example exists
# Or create manually:
```

Edit `backend/.env`:
```
DATABASE_URL=postgresql://your_username:your_password@localhost:5432/nba_betting
```

**Common formats:**
- Default user: `postgresql://postgres:postgres@localhost:5432/nba_betting`
- Custom user: `postgresql://nba_user:password@localhost:5432/nba_betting`
- Mac default: `postgresql://your_mac_username@localhost:5432/nba_betting`

## Step 4: Test Database Connection

```bash
python scripts/test_database.py
```

This will:
1. ✅ Test connection
2. ✅ Create all tables
3. ✅ Verify table structure
4. ✅ Test relationships

## Step 5: Seed Initial Data

Once database is connected and tables are created:

```bash
# Seed teams (30 NBA teams)
python scripts/seed_teams.py

# Seed seasons (current + previous)
python scripts/seed_seasons.py
```

## Troubleshooting

### "role does not exist"
- On Mac, you might need to use your Mac username instead of "postgres"
- Try: `postgresql://your_mac_username@localhost:5432/nba_betting`

### "database does not exist"
- Create the database: `CREATE DATABASE nba_betting;`

### "connection refused"
- PostgreSQL might not be running
- Start it: `brew services start postgresql` (Mac) or `sudo systemctl start postgresql` (Linux)

### "password authentication failed"
- Check your password in `.env` file
- Try resetting PostgreSQL password

## Quick Test

Once database is set up, run:
```bash
python scripts/test_database.py
```

You should see:
```
✅ Database connection successful!
✅ All 13 expected tables exist!
✅ Table structures verified!
✅ Model relationships verified!
🎉 All tests passed! Database is ready.
```

---

**Next Steps After Database Setup:**
1. Run test script to verify everything works
2. Seed teams and seasons
3. Move to Phase 2: Data Collection





