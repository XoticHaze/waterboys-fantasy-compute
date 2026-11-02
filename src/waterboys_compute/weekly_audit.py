from __future__ import annotations

"""Hindsight-only scorecard, not authority to move already-locked players."""

from datetime import datetime

from .live_projection import STARTER_SLOTS, estimate_player_finish


def weekly_lineup_audit(waterboys: dict, as_of: datetime) -> dict:
    roster = list(waterboys.get("roster") or [])
    starters = [
        p for p in roster
        if str(p.get("lineup_slot") or "").upper() in STARTER_SLOTS
    ]
    bench = [
        p for p in roster
        if str(p.get("lineup_slot") or "").upper() == "BE"
    ]
    final = {
        p.get("player_id"): estimate_player_finish(p, as_of)["mode"] == "completed"
        for p in roster
    }
    scored_starters = [p for p in starters if final.get(p.get("player_id"))]
    pending = len(starters) - len(scored_starters)

    projection_errors = []
    for player in scored_starters:
        week = player.get("current_week") or {}
        actual = week.get("points")
        projected = week.get("projected_points")
        if not isinstance(actual, (int, float)) or not isinstance(projected, (int, float)):
            continue
        projection_errors.append({
            "player_id": player.get("player_id"),
            "player": player.get("name"),
            "position": player.get("position"),
            "projected": projected,
            "actual": actual,
            "delta": round(actual - projected, 4),
        })

    opportunities = []
    for benched in bench:
        if not final.get(benched.get("player_id")):
            continue
        bench_points = (benched.get("current_week") or {}).get("points")
        if not isinstance(bench_points, (int, float)):
            continue
        same_position = [
            p for p in scored_starters
            if p.get("position") == benched.get("position")
            and isinstance((p.get("current_week") or {}).get("points"), (int, float))
        ]
        if not same_position:
            continue
        lowest = min(same_position, key=lambda p: p["current_week"]["points"])
        lost = bench_points - lowest["current_week"]["points"]
        if lost <= 0:
            continue
        opportunities.append({
            "bench_player": benched.get("name"),
            "bench_player_id": benched.get("player_id"),
            "starter_player": lowest.get("name"),
            "starter_player_id": lowest.get("player_id"),
            "position": benched.get("position"),
            "bench_actual": bench_points,
            "starter_actual": lowest["current_week"]["points"],
            "hindsight_gain": round(lost, 4),
            "basis": "same_position_completed_games_hindsight_only",
        })

    return {
        "status": "partial" if pending else "finished",
        "hindsight_only": True,
        "starter_count": len(starters),
        "completed_starters": len(scored_starters),
        "pending_starters": pending,
        "projection_errors": sorted(projection_errors, key=lambda row: row["delta"])[:12],
        "bench_opportunities": sorted(
            opportunities, key=lambda row: row["hindsight_gain"], reverse=True
        )[:10],
        "note": "Observed score gaps do not establish that a pre-game alternative was predictable.",
    }
