from __future__ import annotations

"""Live, explicitly heuristic knockout finish estimates.

Do not confuse ESPN's full-week projections with remaining-game forecasts.
The estimator uses actual scored points for completed games, retains future
projections, and interpolates for games underway. It never declares a result
final or a survival probability calibrated from these estimates.
"""

from datetime import datetime, timezone
from typing import Any

STARTER_SLOTS = {"QB", "RB", "WR", "TE", "RB/WR/TE", "FLEX", "D/ST", "K"}
GAME_DURATION_MINUTES = 240
BLOCKED_STATUSES = {"OUT", "INJURY_RESERVE", "DOUBTFUL", "SUSPENDED"}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _start_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        start = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if start.tzinfo is None:
        # espn-api football.schedule dates are UTC strings without a suffix.
        start = start.replace(tzinfo=timezone.utc)
    return start.astimezone(timezone.utc)


def estimate_player_finish(player: dict, as_of: datetime) -> dict:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone aware")
    week = player.get("current_week") or {}
    scored = _number(week.get("points"))
    projected = _number(week.get("projected_points"))
    start = _start_time(week.get("date"))
    now = as_of.astimezone(timezone.utc)
    injury = str(player.get("injury_status") or "").upper()

    if start is None:
        if scored is not None:
            return {"estimated_points": scored, "mode": "score_without_schedule", "uncertain": True}
        if projected is not None:
            return {"estimated_points": projected, "mode": "projection_without_schedule", "uncertain": projected > 0}
        return {"estimated_points": None, "mode": "missing_data", "uncertain": True}

    elapsed = (now - start).total_seconds() / 60
    if elapsed < 0:
        if scored is not None and scored != 0:
            return {"estimated_points": scored, "mode": "score_before_kickoff", "uncertain": True}
        if injury in BLOCKED_STATUSES:
            return {"estimated_points": 0.0, "mode": "inactive", "uncertain": False}
        return {"estimated_points": projected, "mode": "not_started", "uncertain": projected is None}

    if elapsed >= GAME_DURATION_MINUTES:
        if scored is not None:
            return {"estimated_points": scored, "mode": "completed", "uncertain": False}
        if projected == 0 or injury in BLOCKED_STATUSES:
            return {"estimated_points": 0.0, "mode": "inactive", "uncertain": False}
        return {"estimated_points": projected, "mode": "missing_completed_score", "uncertain": True}

    if scored is None:
        return {"estimated_points": projected, "mode": "live_score_missing", "uncertain": True}
    if projected is None:
        return {"estimated_points": scored, "mode": "live_projection_missing", "uncertain": True}
    remaining = max(0.0, 1.0 - elapsed / GAME_DURATION_MINUTES)
    estimated = scored + max(0.0, projected - scored) * remaining
    return {"estimated_points": round(estimated, 4), "mode": "in_progress_estimate", "uncertain": True}


def attach_live_finish(teams: list[dict], as_of: datetime) -> None:
    for team in teams:
        starters = [
            player for player in team.get("roster") or []
            if str(player.get("lineup_slot") or "").upper() in STARTER_SLOTS
        ]
        estimates = [estimate_player_finish(p, as_of) for p in starters]
        missing = sum(row["estimated_points"] is None for row in estimates)
        if not starters or missing:
            team["current_week_live_estimated_points"] = None
        else:
            team["current_week_live_estimated_points"] = round(
                sum(row["estimated_points"] for row in estimates), 4
            )
        team["live_finish_quality"] = {
            "starter_count": len(starters),
            "missing_starter_estimates": missing,
            "uncertain_starter_estimates": sum(row["uncertain"] for row in estimates),
            "modes": {
                mode: sum(row["mode"] == mode for row in estimates)
                for mode in sorted({row["mode"] for row in estimates})
            },
        }


def live_survival_forecast(teams: list[dict], waterboys_team_id: int | None) -> dict:
    alive = [t for t in teams if int(t.get("roster_count") or 0) > 0]
    if not alive or any(_number(t.get("current_week_live_estimated_points")) is None for t in alive):
        return {
            "status": "unavailable",
            "reason": "missing_estimated_starter_points",
            "ranking": [],
            "waterboys_rank": None,
            "cutline_points": None,
            "waterboys_margin": None,
        }

    ranked = sorted(
        alive,
        key=lambda t: (-float(t["current_week_live_estimated_points"]), str(t.get("team_id"))),
    )
    cutoff = float(ranked[-1]["current_week_live_estimated_points"])
    ranking = []
    for place, team in enumerate(ranked, start=1):
        ranking.append({
            "team_id": team.get("team_id"),
            "name": team.get("name"),
            "points": team.get("current_week_points"),
            "rank": team.get("current_week_rank"),
            "projected_points": team.get("current_week_live_estimated_points"),
            "projection_rank": place,
            "original_week_projection": team.get("current_week_projected_points"),
            "estimate_quality": team.get("live_finish_quality"),
        })

    own = next((row for row in ranking if row["team_id"] == waterboys_team_id), None)
    uncertainty = sum(
        int((t.get("live_finish_quality") or {}).get("uncertain_starter_estimates") or 0)
        for t in alive
    )
    return {
        "status": "estimated" if uncertainty == 0 else "estimated_with_uncertainty",
        "method": "earned_points_plus_remaining_scheduled_games; 240-minute in-game interpolation",
        "calibrated_probability": False,
        "ranking": ranking,
        "waterboys_rank": own["projection_rank"] if own else None,
        "cutline_points": round(cutoff, 4),
        "waterboys_margin": round(float(own["projected_points"]) - cutoff, 4) if own else None,
        "uncertain_starter_estimates": uncertainty,
    }
