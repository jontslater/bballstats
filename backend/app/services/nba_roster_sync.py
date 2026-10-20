"""Sync NBA player current_team_id from ESPN team rosters."""
from __future__ import annotations

from typing import Dict

from sqlalchemy.orm import Session

from app.models import Player, Team
from app.scrapers.espn_nba_client import ESPNNBAClient, ESPN_NBA_TEAM_ID_TO_ABBREV
from app.services.nba_results import get_or_create_nba_player


def sync_nba_rosters_from_espn(db: Session, client: ESPNNBAClient = None) -> Dict[str, int]:
    client = client or ESPNNBAClient(delay=0.35)
    teams_data = client._get_json(f"{client.BASE_URL}/teams")
    updated = created = errors = 0
    if not teams_data:
        return {"updated": 0, "created": 0, "errors": 1}

    team_entries = (
        teams_data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    )
    abbrev_to_team = {
        t.abbreviation: t for t in db.query(Team).filter(Team.sport == "NBA").all()
    }

    for entry in team_entries:
        team_meta = entry.get("team", {})
        espn_team_id = str(team_meta.get("id", ""))
        abbrev = ESPN_NBA_TEAM_ID_TO_ABBREV.get(espn_team_id)
        team = abbrev_to_team.get(abbrev) if abbrev else None
        if not team:
            errors += 1
            continue
        roster = client._get_json(f"{client.BASE_URL}/teams/{espn_team_id}/roster")
        if not roster:
            errors += 1
            continue
        for athlete in roster.get("athletes", []):
            try:
                name = athlete.get("displayName") or athlete.get("fullName")
                if not name:
                    continue
                espn_pid = str(athlete.get("id", ""))
                pos = (athlete.get("position") or {}).get("abbreviation")
                before_team = None
                existing = (
                    db.query(Player)
                    .filter(Player.sport == "NBA", Player.espn_player_id == espn_pid)
                    .first()
                )
                if existing:
                    before_team = existing.current_team_id
                player = get_or_create_nba_player(db, name, team, espn_player_id=espn_pid, position=pos)
                if existing is None:
                    created += 1
                elif before_team != player.current_team_id:
                    updated += 1
            except Exception:
                errors += 1
    db.commit()
    return {"updated": updated, "created": created, "errors": errors}
