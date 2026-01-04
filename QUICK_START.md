# Quick Start Guide

Get up and running in 30 minutes!

> **Quick Reference**: See [BACKEND_COMMANDS.md](./BACKEND_COMMANDS.md) for backend start commands.

## Prerequisites Check

First, verify you have everything installed:

```bash
# Check Python version (need 3.9+)
python3 --version

# Check Node.js version (need 16+)
node --version

# Check if PostgreSQL is installed
psql --version

# Check if Git is installed
git --version
```

If anything is missing, install it before proceeding.

---

## Step 1: Clone/Initialize Repository (2 min)

```bash
# If starting fresh
cd /path/to/bballstats
git init
git add .
git commit -m "Initial commit"
```

---

## Step 2: Set Up Backend (10 min)

```bash
# Navigate to backend
cd backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Mac/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file from example
cp .env.example .env

# Edit .env file with your database credentials
# DATABASE_URL=postgresql://username:password@localhost:5432/nba_betting
```

---

## Step 3: Set Up Database (5 min)

```bash
# Start PostgreSQL (if not running)
# On Mac: brew services start postgresql
# On Linux: sudo systemctl start postgresql
# On Windows: Start PostgreSQL service

# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE nba_betting;

# Create user (optional, can use default)
CREATE USER nba_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE nba_betting TO nba_user;

# Exit psql
\q
```

---

## Step 4: Set Up Frontend (5 min)

```bash
# Navigate to frontend
cd ../frontend

# Initialize React app (choose one):
# Option A: Create React App
npx create-react-app . --template typescript

# Option B: Vite (faster, recommended)
npm create vite@latest . -- --template react-ts

# Install dependencies
npm install

# Install additional packages
npm install axios react-router-dom recharts

# Test that it runs
npm start
# Should open http://localhost:3000
```

---

## Step 5: Test Backend Connection (3 min)

```bash
# Go back to backend
cd ../backend

# Make sure virtual environment is activated
source venv/bin/activate  # Mac/Linux
# or
# venv\Scripts\activate  # Windows

# Test database connection
python -c "from app.database import engine; engine.connect(); print('✅ Database connection successful!')"
```

---

## Step 6: Create Initial Database Tables (5 min)

```bash
# Run database migrations (once you create them)
# For now, you can test with:
python -c "from app.database import Base, engine; Base.metadata.create_all(engine); print('✅ Tables created!')"
```

---

## You're Ready! 🎉

Now you can start following the **EXECUTION_PLAN.md** step by step.

### Next Steps:

1. **Phase 1, Step 1.5**: Create all database models
2. **Phase 1, Step 1.6**: Seed basic data (teams, seasons)
3. **Phase 2**: Start collecting data

### Useful Commands:

```bash
# Start backend server
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# Start frontend
cd frontend
npm start

# Run update script (once implemented)
cd scripts
python update_all.py
```

---

## Troubleshooting

### Database Connection Issues
- Check PostgreSQL is running: `psql -U postgres -c "SELECT 1;"`
- Verify DATABASE_URL in `.env` file
- Check username/password are correct

### Python Import Errors
- Make sure virtual environment is activated
- Verify all dependencies installed: `pip list`
- Check you're in the right directory

### Frontend Won't Start
- Delete `node_modules` and `package-lock.json`
- Run `npm install` again
- Check Node.js version: `node --version` (need 16+)

### Port Already in Use
- Backend (8000): Change in `.env` or kill process: `lsof -ti:8000 | xargs kill`
- Frontend (3000): Change in `package.json` or kill process: `lsof -ti:3000 | xargs kill`

---

## Need Help?

- Check **EXECUTION_PLAN.md** for detailed steps
- Review **PROJECT_OUTLINE.md** for architecture details
- See **GAP_ANALYSIS.md** for feature recommendations

Good luck! 🏀

