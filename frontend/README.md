# NBA Betting Analytics - Frontend

React + TypeScript frontend for the NBA Betting Analytics platform.

## Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Development

The frontend runs on `http://localhost:3000` and proxies API requests to `http://localhost:8000`.

Make sure the backend API is running:
```bash
cd ../backend
source venv/bin/activate
uvicorn app.main:app --reload
```

## Features

- **Dashboard**: View today's games, safe bets, and long shots
- **Games List**: Browse all games by date
- **Game Detail**: View all predictions for a game, create plays
- **My Plays**: Track your betting plays and performance

## API Integration

All API calls are handled through `src/services/api.ts`. The frontend automatically connects to the backend API.


