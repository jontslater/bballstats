# Backend Commands Quick Reference

## Starting the Backend

### From Project Root
```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --reload
```

### From Backend Directory
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

### One-Liner (Full Path)
```bash
cd /Users/lisaannparr/bballstats/backend && source venv/bin/activate && uvicorn app.main:app --reload
```

## What Each Part Does

- `cd backend` - Navigate to backend directory
- `source venv/bin/activate` - Activate Python virtual environment
- `uvicorn app.main:app --reload` - Start FastAPI server with auto-reload

## Backend URL

Once started, the backend runs at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Stopping the Backend

Press `Ctrl+C` in the terminal where it's running.

## Frontend Commands (For Reference)

The frontend uses npm (different from backend):

```bash
cd frontend
npm install  # First time only
npm run dev  # Start frontend dev server
```

Frontend runs at: http://localhost:3000

## Quick Start Both Servers

**Terminal 1 (Backend):**
```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend && npm run dev
```

## Common Issues

**"uvicorn: command not found"**
- Make sure virtual environment is activated: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**"Module not found"**
- Make sure you're in the backend directory
- Virtual environment should be activated

**Port already in use**
- Another instance might be running
- Kill the process or use a different port: `uvicorn app.main:app --reload --port 8001`


