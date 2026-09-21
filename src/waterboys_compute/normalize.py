from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _attr(node: Any, *names: str, default=None):
    for name in names:
        if hasattr(node, name):
            value = getattr(node, name)
            if value is not None:
                return value
    return default


def _json_scalar(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def player_node(player: Any) -> dict:
    return {
        "player_id": _attr(player, "playerId", "player_id"),
        "name": _attr(player, "name"),
        "position": _attr(player, "position"),
        "pro_team": _attr(player, "proTeam", "pro_team"),
        "lineup_slot": _json_scalar(_attr(player, "lineupSlot", "lineup_slot")),
        "injury_status": _json_scalar(_attr(player, "injuryStatus", "injury_status")),
        "projected_points": _attr(player, "projected_total_points", "projected_points"),
        "total_points": _attr(player, "total_points"),
        "percent_owned": _attr(player, "percent_owned"),
        "percent_started": _attr(player, "percent_started"),
    }


def team_node(team: Any) -> dict:
    roster = list(_attr(team, "roster", default=[]) or [])
    return {
        "team_id": _attr(team, "team_id", "teamId"),
        "name": _attr(team, "team_name", "teamName"),
        "owner": _json_scalar(_attr(team, "owner")),
        "wins": _attr(team, "wins", default=0),
        "losses": _attr(team, "losses", default=0),
        "ties": _attr(team, "ties", default=0),
        "points_for": _attr(team, "points_for", "pointsFor"),
        "points_against": _attr(team, "points_against", "pointsAgainst"),
        "acquisition_budget_spent": _attr(team, "acquisition_budget_spent", default=None),
        "waiver_rank": _attr(team, "waiver_rank", default=None),
        "roster": [player_node(player) for player in roster],
    }


def box_score_node(box: Any) -> dict:
    home = _attr(box, "home_team")
    away = _attr(box, "away_team")
    return {
        "home_team_id": _attr(home, "team_id", "teamId") if home else None,
        "home_team": _attr(home, "team_name", "teamName") if home else None,
        "home_score": _attr(box, "home_score"),
        "away_team_id": _attr(away, "team_id", "teamId") if away else None,
        "away_team": _attr(away, "team_name", "teamName") if away else None,
        "away_score": _attr(box, "away_score"),
    }


def activity_node(activity: Any) -> dict:
    actions = []
    for item in list(_attr(activity, "actions", default=[]) or []):
        if isinstance(item, (list, tuple)):
            actions.append([_json_scalar(x) if not hasattr(x, "name") else _attr(x, "name") for x in item])
        else:
            actions.append(_json_scalar(item))
    return {
        "date": _json_scalar(_attr(activity, "date")),
        "actions": actions,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
