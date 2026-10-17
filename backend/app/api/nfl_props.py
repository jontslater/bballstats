"""NFL prop pricing against sportsbook lines."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.database import get_db
from app.services.nfl_prop_pricing import NFLPropPricingService, ODDS_API_MARKET_MAP
from sqlalchemy.orm import Session

router = APIRouter(prefix="/nfl/props", tags=["NFL Props"])


class PropPriceRequest(BaseModel):
    player_name: str
    stat_type: str = Field(description="Internal stat or The Odds API market key")
    line: float
    sportsbook_odds: Optional[str] = Field(None, description="American odds e.g. -115 or +120")
    game_id: Optional[int] = None
    team_abbrev: Optional[str] = None


@router.get("/markets")
def list_market_mappings():
    return ODDS_API_MARKET_MAP


@router.post("/price")
def price_prop(body: PropPriceRequest, db: Session = Depends(get_db)):
    service = NFLPropPricingService(db)
    try:
        result = service.price_prop(
            player_name=body.player_name,
            stat_type=body.stat_type,
            line=body.line,
            sportsbook_odds=body.sportsbook_odds,
            game_id=body.game_id,
            team_abbrev=body.team_abbrev,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "player_name": result.player_name,
        "stat_type": result.stat_type,
        "line": result.line,
        "model_probability": result.model_probability,
        "calibrated_probability": result.calibrated_probability,
        "break_even_american_odds": result.break_even_american_odds,
        "sportsbook_american_odds": result.sportsbook_american_odds,
        "implied_probability": result.implied_probability,
        "edge": result.edge,
        "sample_size": result.sample_size,
        "player_mean": result.player_mean,
        "player_std": result.player_std,
    }
