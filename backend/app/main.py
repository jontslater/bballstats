"""
FastAPI main application file.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, init_db
from app.api import predictions, games, players, plays, analytics, export, lineups, parlays, suggested_bets, historical_results, game_results, betting_lines, advanced_bets, analyze, ml_training, updates, poor_mans_bet, bankroll_recommendations

# Create FastAPI app
app = FastAPI(
    title="NBA Betting Analytics API",
    description="API for NBA player statistics and betting predictions",
    version="1.0.0"
)

# Configure CORS (allow frontend to connect)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"],  # React/Vite ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "message": "NBA Betting Analytics API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    try:
        # Test database connection
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


# Include routers
app.include_router(predictions.router)
app.include_router(games.router)
app.include_router(players.router)
app.include_router(plays.router)
app.include_router(analytics.router)
app.include_router(export.router)
app.include_router(lineups.router)
app.include_router(parlays.router)
app.include_router(suggested_bets.router)
app.include_router(historical_results.router)
app.include_router(game_results.router)
app.include_router(betting_lines.router)
app.include_router(advanced_bets.router)
app.include_router(analyze.router)
app.include_router(ml_training.router)
app.include_router(updates.router)
app.include_router(poor_mans_bet.router)
app.include_router(bankroll_recommendations.router)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on startup."""
    try:
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"⚠️  Database initialization warning: {e}")
        print("   (This is normal if database doesn't exist yet or tables already exist)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

