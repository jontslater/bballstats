"""
Ingest and query MLB Statcast daily rollups for luck adjustment.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models import MlbStatcastDaily, Player
from app.scrapers.statcast_client import StatcastClient
from app.services.mlb_luck_adjustment import aggregate_daily_rows, metrics_from_totals


def rollup_batted_ball_rows(rows: Iterable[Dict], game_date: date, season: int) -> Dict[int, Dict]:
    """Aggregate parsed Savant rows into per-batter daily totals."""
    per_batter: Dict[int, Dict] = {}
    for row in rows:
        if not row.get("is_bip"):
            continue
        batter_id = int(row.get("batter_id") or 0)
        if batter_id <= 0:
            continue
        bucket = per_batter.setdefault(
            batter_id,
            {
                "mlbam_id": batter_id,
                "game_date": game_date,
                "season": season,
                "bip": 0,
                "hits_on_bip": 0,
                "total_bases_on_bip": 0,
                "sum_est_ba": 0.0,
                "sum_est_slg": 0.0,
                "sum_est_woba": 0.0,
                "sum_woba_value": 0.0,
                "sum_woba_denom": 0.0,
                "hr_on_bip": 0,
                "hard_hit_count": 0,
                "barrel_count": 0,
                "launch_speed_sum": 0.0,
            },
        )
        bucket["bip"] += 1
        if row.get("is_hit"):
            bucket["hits_on_bip"] += 1
        bucket["total_bases_on_bip"] += int(row.get("total_bases") or 0)
        bucket["sum_est_ba"] += float(row.get("est_ba") or 0.0)
        bucket["sum_est_slg"] += float(row.get("est_slg") or 0.0)
        bucket["sum_est_woba"] += float(row.get("est_woba") or 0.0)
        bucket["sum_woba_value"] += float(row.get("woba_value") or 0.0)
        bucket["sum_woba_denom"] += float(row.get("woba_denom") or 0.0)
        if row.get("is_hr"):
            bucket["hr_on_bip"] += 1
        ls = row.get("launch_speed")
        if ls is not None:
            bucket["launch_speed_sum"] += float(ls)
            if float(ls) >= 95.0:
                bucket["hard_hit_count"] += 1
        if row.get("launch_speed_angle") == 6:
            bucket["barrel_count"] += 1
    return per_batter


def upsert_daily_rollups(db: Session, rollups: Dict[int, Dict]) -> int:
    """Insert or update daily statcast rows. Returns number of rows touched."""
    if not rollups:
        return 0
    mlbam_ids = list(rollups.keys())
    player_map = {
        p.mlbam_id: p.player_id
        for p in db.query(Player).filter(
            Player.sport == "MLB", Player.mlbam_id.in_(mlbam_ids)
        )
    }
    touched = 0
    for mlbam_id, payload in rollups.items():
        existing = (
            db.query(MlbStatcastDaily)
            .filter(
                MlbStatcastDaily.mlbam_id == mlbam_id,
                MlbStatcastDaily.game_date == payload["game_date"],
            )
            .first()
        )
        if existing:
            for field in (
                "bip",
                "hits_on_bip",
                "total_bases_on_bip",
                "sum_est_ba",
                "sum_est_slg",
                "sum_est_woba",
                "sum_woba_value",
                "sum_woba_denom",
                "hr_on_bip",
                "hard_hit_count",
                "barrel_count",
                "launch_speed_sum",
                "season",
            ):
                setattr(existing, field, payload[field])
            existing.player_id = player_map.get(mlbam_id)
            touched += 1
        else:
            db.add(
                MlbStatcastDaily(
                    mlbam_id=mlbam_id,
                    player_id=player_map.get(mlbam_id),
                    game_date=payload["game_date"],
                    season=payload["season"],
                    bip=payload["bip"],
                    hits_on_bip=payload["hits_on_bip"],
                    total_bases_on_bip=payload["total_bases_on_bip"],
                    sum_est_ba=payload["sum_est_ba"],
                    sum_est_slg=payload["sum_est_slg"],
                    sum_est_woba=payload["sum_est_woba"],
                    sum_woba_value=payload["sum_woba_value"],
                    sum_woba_denom=payload["sum_woba_denom"],
                    hr_on_bip=payload["hr_on_bip"],
                    hard_hit_count=payload["hard_hit_count"],
                    barrel_count=payload["barrel_count"],
                    launch_speed_sum=payload["launch_speed_sum"],
                )
            )
            touched += 1
    db.commit()
    return touched


def ingest_statcast_for_date(db: Session, game_date: date, season: int, client: Optional[StatcastClient] = None) -> int:
    client = client or StatcastClient()
    rows = client.fetch_batted_balls_for_date(game_date, season)
    rollups = rollup_batted_ball_rows(rows, game_date, season)
    return upsert_daily_rollups(db, rollups)


def ingest_statcast_range(
    db: Session,
    start_date: date,
    end_date: date,
    season: int,
    skip_existing: bool = True,
) -> Dict[str, int]:
    client = StatcastClient()
    stats = {"days": 0, "rows": 0, "skipped": 0}
    current = start_date
    while current <= end_date:
        if skip_existing:
            exists = (
                db.query(MlbStatcastDaily.id)
                .filter(MlbStatcastDaily.game_date == current)
                .first()
            )
            if exists:
                stats["skipped"] += 1
                current += timedelta(days=1)
                continue
        try:
            touched = ingest_statcast_for_date(db, current, season, client=client)
            stats["rows"] += touched
            stats["days"] += 1
        except Exception as exc:
            print(f"  Statcast ingest failed for {current}: {exc}")
        current += timedelta(days=1)
    return stats


def get_luck_metrics_for_player(
    db: Session,
    player_id: int,
    before_date: date,
    season: Optional[int] = None,
) -> Optional[Dict[str, float]]:
    player = db.query(Player).filter(Player.player_id == player_id).first()
    if not player or not player.mlbam_id:
        return None
    return get_luck_metrics_for_mlbam(db, player.mlbam_id, before_date, season=season)


def get_luck_metrics_for_mlbam(
    db: Session,
    mlbam_id: int,
    before_date: date,
    season: Optional[int] = None,
) -> Optional[Dict[str, float]]:
    query = db.query(MlbStatcastDaily).filter(
        MlbStatcastDaily.mlbam_id == mlbam_id,
        MlbStatcastDaily.game_date < before_date,
    )
    if season is not None:
        query = query.filter(MlbStatcastDaily.season == season)
    rows = query.all()
    if not rows:
        return None
    totals_map = aggregate_daily_rows(rows)
    totals = totals_map.get(mlbam_id)
    if not totals:
        return None
    return metrics_from_totals(totals)


def link_player_mlbam_id(db: Session, player: Player, mlbam_id: int) -> bool:
    """
    Attach MLBAM id to player when unambiguous. Never overwrite an existing different id
    or steal an id already assigned to another player.
    """
    if not mlbam_id or mlbam_id <= 0:
        return False
    conflict = (
        db.query(Player)
        .filter(
            Player.sport == "MLB",
            Player.mlbam_id == mlbam_id,
            Player.player_id != player.player_id,
        )
        .first()
    )
    if conflict:
        return False
    if player.mlbam_id and player.mlbam_id != mlbam_id:
        return False
    if player.mlbam_id != mlbam_id:
        player.mlbam_id = mlbam_id
    db.query(MlbStatcastDaily).filter(MlbStatcastDaily.mlbam_id == mlbam_id).update(
        {MlbStatcastDaily.player_id: player.player_id}, synchronize_session=False
    )
    return True
