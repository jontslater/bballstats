"""
Remove duplicate NBA prediction rows (one row per player/game/stat).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from app.models.prediction import Prediction

BET_TYPE_RANK = {"safe": 0, "standard": 1, "long_shot": 2, "pass": 3}


def dedupe_nba_predictions(db: Session, dry_run: bool = False) -> Dict[str, int]:
    """
    Keep a single prediction per (player_id, game_id, stat_type) for NBA.
    Prefers bet_type safe, then standard, then long_shot; lowest prediction_id wins ties.
    """
    rows = (
        db.query(Prediction)
        .filter(Prediction.sport == "NBA", Prediction.bet_type != "pass")
        .order_by(Prediction.prediction_id)
        .all()
    )
    groups: Dict[Tuple[int, int, str], list] = defaultdict(list)
    for row in rows:
        groups[(row.player_id, row.game_id, row.stat_type)].append(row)

    deleted = kept = 0
    for _key, preds in groups.items():
        if len(preds) <= 1:
            kept += 1
            continue
        preds.sort(
            key=lambda p: (
                BET_TYPE_RANK.get(p.bet_type or "pass", 99),
                p.prediction_id,
            )
        )
        keep = preds[0]
        for extra in preds[1:]:
            if not dry_run:
                db.delete(extra)
            deleted += 1
        kept += 1

    if not dry_run and deleted:
        db.commit()
    return {"groups": len(groups), "kept": kept, "deleted": deleted}
