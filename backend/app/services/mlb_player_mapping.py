"""
MLBAM id resolution for MLB players (box-score short names, roster CSV, Stats API).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Player, Team
from app.scrapers.mlb_api_client import MLB_TEAM_ID_TO_ABBREV

# Reverse: our abbrev -> MLB API team id
ABBREV_TO_MLB_TEAM_ID = {v: k for k, v in MLB_TEAM_ID_TO_ABBREV.items()}


@dataclass
class MlbamCandidate:
    mlbam_id: int
    full_name: str
    last_name: str
    first_initial: str
    boxscore_name: str
    team_abbrev: Optional[str]


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_token(text: str) -> str:
    text = _strip_accents(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_boxscore_name(name: str) -> Tuple[str, str]:
    """
    Parse Stats API / Savant style names into (last, first_initial).

    Examples: 'Marsh' -> ('marsh', ''), 'Murphy, C' -> ('murphy', 'c'), 'Judge, A' -> ('judge', 'a')
    """
    raw = (name or "").strip()
    if not raw:
        return "", ""
    if "," in raw:
        last, first = raw.split(",", 1)
        last = normalize_token(last)
        first = normalize_token(first)
        return last, (first[:1] if first else "")
    parts = normalize_token(raw).split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], parts[0][:1]


def candidate_from_statsapi(entry: Dict) -> Optional[MlbamCandidate]:
    try:
        mlbam_id = int(entry["id"])
    except (KeyError, TypeError, ValueError):
        return None
    full_name = entry.get("fullName") or entry.get("nameFirstLast") or ""
    last_name = normalize_token(entry.get("lastName") or "")
    first_initial = normalize_token(entry.get("firstName") or "")[:1]
    boxscore = entry.get("boxscoreName") or entry.get("useName") or ""
    team_id = (entry.get("currentTeam") or {}).get("id")
    team_abbrev = MLB_TEAM_ID_TO_ABBREV.get(team_id) if team_id else None
    if not last_name and full_name:
        last_name, first_initial = parse_boxscore_name(full_name)
    return MlbamCandidate(
        mlbam_id=mlbam_id,
        full_name=full_name,
        last_name=last_name,
        first_initial=first_initial,
        boxscore_name=boxscore,
        team_abbrev=team_abbrev,
    )


def load_candidates_from_statsapi(season: int) -> List[MlbamCandidate]:
    import requests

    url = "https://statsapi.mlb.com/api/v1/sports/1/players"
    response = requests.get(
        url,
        params={"season": season, "activeStatus": "ACTIVE"},
        timeout=60,
    )
    response.raise_for_status()
    people = response.json().get("people") or []
    out = []
    for entry in people:
        cand = candidate_from_statsapi(entry)
        if cand:
            out.append(cand)
    return out


def load_candidates_from_savant_csv(csv_text: str) -> List[MlbamCandidate]:
    reader = csv.DictReader(io.StringIO(csv_text))
    out = []
    for row in reader:
        try:
            mlbam_id = int(row.get("player_id") or 0)
        except ValueError:
            continue
        if mlbam_id <= 0:
            continue
        name_field = row.get('"last_name, first_name"') or row.get("last_name, first_name") or ""
        name_field = name_field.strip('"')
        last, first = parse_boxscore_name(name_field.replace('"', ""))
        out.append(
            MlbamCandidate(
                mlbam_id=mlbam_id,
                full_name=name_field,
                last_name=last,
                first_initial=first,
                boxscore_name=last,
                team_abbrev=None,
            )
        )
    return out


def _team_abbrev_for_player(db: Session, player: Player) -> Optional[str]:
    if not player.current_team_id:
        return None
    team = db.query(Team).filter(Team.team_id == player.current_team_id).first()
    return team.abbreviation if team else None


def score_player_candidate(
    player: Player,
    candidate: MlbamCandidate,
    team_abbrev: Optional[str],
) -> float:
    p_last, p_first = parse_boxscore_name(player.name)
    score = 0.0
    if p_last and candidate.last_name and p_last == candidate.last_name:
        score += 3.0
    elif p_last and candidate.last_name and p_last in candidate.last_name:
        score += 1.5
    if p_first and candidate.first_initial and p_first == candidate.first_initial:
        score += 2.0
    box_last, box_first = parse_boxscore_name(candidate.boxscore_name)
    if p_last and box_last and p_last == box_last:
        score += 2.0
    if p_first and box_first and p_first == box_first:
        score += 1.0
    if team_abbrev and candidate.team_abbrev and team_abbrev == candidate.team_abbrev:
        score += 1.5
    return score


def best_mlbam_match(
    player: Player,
    candidates: List[MlbamCandidate],
    team_abbrev: Optional[str],
    min_score: float = 4.0,
) -> Optional[int]:
    best_id = None
    best_score = 0.0
    for cand in candidates:
        score = score_player_candidate(player, cand, team_abbrev)
        if score > best_score:
            best_score = score
            best_id = cand.mlbam_id
    if best_score >= min_score:
        return best_id
    return None


def build_mlbam_index(candidates: List[MlbamCandidate]) -> Dict[int, MlbamCandidate]:
    return {c.mlbam_id: c for c in candidates}


def backfill_mlbam_ids(
    db: Session,
    season: int,
    *,
    dry_run: bool = False,
    min_score: float = 4.0,
) -> Dict[str, int]:
    """
    Assign MLBAM ids to MLB players missing them using Stats API roster + Savant CSV.
    """
    from app.scrapers.statcast_client import StatcastClient

    stats = {"examined": 0, "matched": 0, "skipped_has_id": 0, "skipped_conflict": 0, "unmatched": 0}
    candidates = load_candidates_from_statsapi(season)
    try:
        client = StatcastClient(delay=0.25)
        csv_text = client.fetch_expected_stats_leaderboard_csv(season, min_pa=1)
        candidates.extend(load_candidates_from_savant_csv(csv_text))
    except Exception:
        pass

    by_id = build_mlbam_index(candidates)
    taken = {
        p.mlbam_id
        for p in db.query(Player).filter(Player.sport == "MLB", Player.mlbam_id.isnot(None)).all()
    }

    players = (
        db.query(Player)
        .filter(Player.sport == "MLB", Player.mlbam_id.is_(None))
        .order_by(Player.player_id)
        .all()
    )

    for player in players:
        stats["examined"] += 1
        team_abbrev = _team_abbrev_for_player(db, player)
        mlbam_id = best_mlbam_match(player, list(by_id.values()), team_abbrev, min_score=min_score)
        if not mlbam_id:
            stats["unmatched"] += 1
            continue
        if mlbam_id in taken:
            stats["skipped_conflict"] += 1
            continue
        if not dry_run:
            player.mlbam_id = mlbam_id
            taken.add(mlbam_id)
        stats["matched"] += 1

    if not dry_run:
        db.commit()
    return stats
