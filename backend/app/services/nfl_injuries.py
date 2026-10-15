"""
Collect NFL injuries from ESPN game summaries for upcoming games.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import Game, Player, Team
from app.models.injury import Injury
from app.scrapers.espn_nfl_client import ESPNNFLClient
from app.services.nfl_data import map_espn_injury_status
from app.services.nfl_results import get_or_create_nfl_player
from app.services.nfl_schedule import find_nfl_team


def collect_injuries_for_upcoming_games(
    db: Session,
    days_ahead: int = 7,
) -> Dict[str, int]:
    client = ESPNNFLClient()
    today = date.today()
    end = today + timedelta(days=days_ahead)

    games = db.query(Game).filter(
        Game.sport == "NFL",
        Game.game_date >= today,
        Game.game_date <= end,
        Game.game_status.in_(["scheduled", "in_progress"]),
        Game.espn_game_id.isnot(None),
    ).all()

    saved = 0
    seen_games = set()

    for game in games:
        if game.espn_game_id in seen_games:
            continue
        seen_games.add(game.espn_game_id)

        summary = client.get_game_summary(game.espn_game_id)
        if not summary:
            continue

        for inj in client.parse_injuries(summary):
            team = find_nfl_team(db, inj.get("team_abbrev"))
            if not team:
                continue
            player = get_or_create_nfl_player(
                db,
                inj["player_name"],
                team,
                inj.get("position"),
            )
            status = map_espn_injury_status(inj.get("status"))

            existing = db.query(Injury).filter(
                Injury.player_id == player.player_id,
                Injury.injury_date == game.game_date,
            ).first()
            if existing:
                existing.status = status
                existing.injury_type = inj.get("injury_type") or existing.injury_type
                existing.source = "ESPN"
            else:
                db.add(
                    Injury(
                        player_id=player.player_id,
                        injury_date=game.game_date,
                        injury_type=inj.get("injury_type"),
                        status=status,
                        source="ESPN",
                        description=f"ESPN injury report for week of {game.game_date}",
                    )
                )
            saved += 1

    db.commit()
    return {"injury_rows": saved, "games_checked": len(seen_games)}
