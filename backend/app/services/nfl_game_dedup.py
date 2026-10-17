"""
Merge duplicate NFL Game rows (timezone/off-by-one date vs ESPN id).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Game, GameSchedule, PlayerGameStat, Prediction


def find_matching_nfl_game(
    db: Session,
    home_team_id: int,
    away_team_id: int,
    game_date: date,
    espn_game_id: Optional[str] = None,
    day_slop: int = 1,
) -> Optional[Game]:
    if espn_game_id:
        g = db.query(Game).filter(Game.sport == "NFL", Game.espn_game_id == str(espn_game_id)).first()
        if g:
            return g

    start = game_date - timedelta(days=day_slop)
    end = game_date + timedelta(days=day_slop)
    candidates = db.query(Game).filter(
        Game.sport == "NFL",
        Game.home_team_id == home_team_id,
        Game.away_team_id == away_team_id,
        Game.game_date >= start,
        Game.game_date <= end,
    ).all()
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Prefer row with ESPN id, else closest date
    with_espn = [c for c in candidates if c.espn_game_id]
    if with_espn:
        return with_espn[0]
    return min(candidates, key=lambda g: abs((g.game_date - game_date).days))


def _repoint_fk(db: Session, from_id: int, to_id: int) -> None:
    for pgs in db.query(PlayerGameStat).filter(PlayerGameStat.game_id == from_id).all():
        dup = db.query(PlayerGameStat).filter(
            PlayerGameStat.game_id == to_id,
            PlayerGameStat.player_id == pgs.player_id,
        ).first()
        if dup:
            db.delete(pgs)
        else:
            pgs.game_id = to_id
    for pred in db.query(Prediction).filter(Prediction.game_id == from_id).all():
        pred.game_id = to_id
    for sched in db.query(GameSchedule).filter(GameSchedule.game_id == from_id).all():
        if sched.game_id != to_id:
            other = db.query(GameSchedule).filter(GameSchedule.game_id == to_id).first()
            if other:
                db.delete(sched)
            else:
                sched.game_id = to_id


def merge_duplicate_games(db: Session, keep: Game, drop: Game) -> None:
    if keep.game_id == drop.game_id:
        return
    _repoint_fk(db, drop.game_id, keep.game_id)
    if drop.home_score is not None and keep.home_score is None:
        keep.home_score = drop.home_score
        keep.away_score = drop.away_score
    if drop.espn_game_id and not keep.espn_game_id:
        keep.espn_game_id = drop.espn_game_id
    db.delete(drop)


def dedupe_nfl_games(db: Session, season_id: Optional[int] = None) -> Dict[str, int]:
    """Find home/away pairs within ±1 day and merge into canonical ESPN-dated game."""
    q = db.query(Game).filter(Game.sport == "NFL")
    if season_id:
        q = q.filter(Game.season_id == season_id)
    games = q.order_by(Game.game_date).all()

    groups: Dict[Tuple[int, int], List[Game]] = {}
    for g in games:
        key = (g.home_team_id, g.away_team_id)
        groups.setdefault(key, []).append(g)

    merged = 0
    for key, group in groups.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda g: (0 if g.espn_game_id else 1, g.game_date))
        keep = group[0]
        for drop in group[1:]:
            if abs((drop.game_date - keep.game_date).days) > 1:
                continue
            merge_duplicate_games(db, keep, drop)
            merged += 1
        if keep.espn_game_id:
            # Normalize date to latest ESPN sync among cluster
            cluster_dates = [g.game_date for g in group if abs((g.game_date - keep.game_date).days) <= 1]
            if cluster_dates:
                keep.game_date = max(cluster_dates)

    db.commit()
    return {"merged": merged}
