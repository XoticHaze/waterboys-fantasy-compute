from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


BENCH_SLOTS = {"BE", "IR"}


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


def _dict_week(stats: Any, week: int | None) -> dict:
    if not isinstance(stats, dict) or week is None:
        return {}
    for key in (week, str(week)):
        value = stats.get(key)
        if isinstance(value, dict):
            return value
    return {}


def player_node(player: Any, current_week: int | None = None) -> dict:
    stats = _attr(player, "stats", default={}) or {}
    week = _dict_week(stats, current_week)
    schedule = _attr(player, "schedule", default={}) or {}
    schedule_week = {}
    if isinstance(schedule, dict) and current_week is not None:
        schedule_week = schedule.get(current_week) or schedule.get(str(current_week)) or {}
    if not isinstance(schedule_week, dict):
        schedule_week = {}

    return {
        "player_id": _attr(player, "playerId", "player_id"),
        "name": _attr(player, "name"),
        "position": _attr(player, "position"),
        "eligible_slots": list(_attr(player, "eligibleSlots", "eligible_slots", default=[]) or []),
        "pro_team": _attr(player, "proTeam", "pro_team"),
        "lineup_slot": _json_scalar(_attr(player, "lineupSlot", "lineup_slot")),
        "on_team_id": _attr(player, "onTeamId", "on_team_id"),
        "acquisition_type": _json_scalar(_attr(player, "acquisitionType", "acquisition_type")),
        "injury_status": _json_scalar(_attr(player, "injuryStatus", "injury_status")),
        "injured": bool(_attr(player, "injured", default=False)),
        "positional_rank": _attr(player, "posRank", "positional_rank"),
        "total_points": _attr(player, "total_points"),
        "avg_points": _attr(player, "avg_points"),
        "projected_total_points": _attr(player, "projected_total_points"),
        "projected_avg_points": _attr(player, "projected_avg_points"),
        "percent_owned": _attr(player, "percent_owned"),
        "percent_started": _attr(player, "percent_started"),
        "current_week": {
            "week": current_week,
            "points": week.get("points"),
            "projected_points": week.get("projected_points"),
            "opponent": _json_scalar(schedule_week.get("team")),
            "date": _json_scalar(schedule_week.get("date")),
        },
    }


def team_node(team: Any, current_week: int | None = None, acquisition_budget: int | None = None) -> dict:
    roster = list(_attr(team, "roster", default=[]) or [])
    players = [player_node(player, current_week=current_week) for player in roster]
    starters = [player for player in players if str(player.get("lineup_slot") or "") not in BENCH_SLOTS]

    def sum_metric(metric: str):
        values = [player.get("current_week", {}).get(metric) for player in starters]
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        return round(sum(numeric), 4) if numeric else None

    spent = _attr(team, "acquisition_budget_spent", default=None)
    remaining = None
    if isinstance(acquisition_budget, int) and isinstance(spent, int):
        remaining = max(0, acquisition_budget - spent)

    return {
        "team_id": _attr(team, "team_id", "teamId"),
        "abbrev": _attr(team, "team_abbrev", "teamAbbrev"),
        "name": _attr(team, "team_name", "teamName"),
        "wins": _attr(team, "wins", default=0),
        "losses": _attr(team, "losses", default=0),
        "ties": _attr(team, "ties", default=0),
        "standing": _attr(team, "standing", default=None),
        "final_standing": _attr(team, "final_standing", default=None),
        "points_for": _attr(team, "points_for", "pointsFor"),
        "points_against": _attr(team, "points_against", "pointsAgainst"),
        "waiver_rank": _attr(team, "waiver_rank", default=None),
        "acquisitions": _attr(team, "acquisitions", default=None),
        "drops": _attr(team, "drops", default=None),
        "trades": _attr(team, "trades", default=None),
        "moves_to_ir": _attr(team, "move_to_ir", default=None),
        "acquisition_budget_spent": spent,
        "acquisition_budget_remaining": remaining,
        "current_week_points": sum_metric("points"),
        "current_week_projected_points": sum_metric("projected_points"),
        "roster_count": len(players),
        "roster": players,
    }


def activity_node(activity: Any) -> dict:
    normalized = []
    for item in list(_attr(activity, "actions", default=[]) or []):
        if not isinstance(item, (list, tuple)):
            normalized.append({"raw": _json_scalar(item)})
            continue

        team = item[0] if len(item) > 0 else None
        action = item[1] if len(item) > 1 else None
        player = item[2] if len(item) > 2 else None
        bid = item[3] if len(item) > 3 else None

        normalized.append({
            "team_id": _attr(team, "team_id", "teamId"),
            "team": _attr(team, "team_name", "teamName") or _json_scalar(team),
            "action": _json_scalar(action),
            "player_id": _attr(player, "playerId", "player_id"),
            "player": _attr(player, "name") or _json_scalar(player),
            "bid": bid if isinstance(bid, (int, float)) else None,
        })

    return {"date": _json_scalar(_attr(activity, "date")), "actions": normalized}


def settings_node(settings: Any) -> dict:
    return {
        "name": _attr(settings, "name"),
        "team_count": _attr(settings, "team_count"),
        "regular_season_count": _attr(settings, "reg_season_count"),
        "playoff_team_count": _attr(settings, "playoff_team_count"),
        "playoff_matchup_period_length": _attr(settings, "playoff_matchup_period_length"),
        "faab": bool(_attr(settings, "faab", default=False)),
        "acquisition_budget": _attr(settings, "acquisition_budget"),
        "acquisition_limit": _attr(settings, "acquisition_limit"),
        "matchup_acquisition_limit": _attr(settings, "matchup_acquisition_limit"),
        "matchup_limit_per_scoring_period": _attr(settings, "matchup_limit_per_scoring_period"),
        "minimum_bid": _attr(settings, "minimum_bid"),
        "waiver_process_days": list(_attr(settings, "waiver_process_days", default=[]) or []),
        "waiver_process_hour": _attr(settings, "waiver_process_hour"),
        "trade_deadline": _attr(settings, "trade_deadline"),
        "veto_votes_required": _attr(settings, "veto_votes_required"),
        "tie_rule": _attr(settings, "tie_rule"),
        "playoff_tie_rule": _attr(settings, "playoff_tie_rule"),
        "playoff_seed_tie_rule": _attr(settings, "playoff_seed_tie_rule"),
        "scoring_format": list(_attr(settings, "scoring_format", default=[]) or []),
    }


def survival_node(teams: list[dict], waterboys_team_id: int | None) -> dict:
    eliminated = [team for team in teams if int(team.get("roster_count") or 0) == 0]
    alive = [team for team in teams if int(team.get("roster_count") or 0) > 0]

    ranked_projection = sorted(
        alive,
        key=lambda team: (
            team.get("current_week_projected_points") is None,
            -(float(team.get("current_week_projected_points") or 0)),
        ),
    )
    for rank, team in enumerate(ranked_projection, start=1):
        team["current_week_projection_rank"] = rank

    numeric_actual = [
        float(team["current_week_points"])
        for team in alive
        if isinstance(team.get("current_week_points"), (int, float))
    ]
    has_actual = bool(numeric_actual)

    ranked_actual = sorted(
        alive,
        key=lambda team: (
            team.get("current_week_points") is None,
            -(float(team.get("current_week_points") or 0)),
        ),
    )
    if has_actual:
        for rank, team in enumerate(ranked_actual, start=1):
            team["current_week_rank"] = rank
    else:
        for team in alive:
            team["current_week_rank"] = None

    cutline = min(numeric_actual) if numeric_actual else None
    projected_values = [
        float(team["current_week_projected_points"])
        for team in alive
        if isinstance(team.get("current_week_projected_points"), (int, float))
    ]
    projected_cutline = min(projected_values) if projected_values else None

    waterboys = next((team for team in alive if team.get("team_id") == waterboys_team_id), None)
    actual_margin = None
    projected_margin = None
    if waterboys and cutline is not None and isinstance(waterboys.get("current_week_points"), (int, float)):
        actual_margin = round(float(waterboys["current_week_points"]) - cutline, 4)
    if (
        waterboys
        and projected_cutline is not None
        and isinstance(waterboys.get("current_week_projected_points"), (int, float))
    ):
        projected_margin = round(
            float(waterboys["current_week_projected_points"]) - projected_cutline,
            4,
        )

    basis = "actual" if has_actual else "projection"
    watch_ranked = ranked_actual if has_actual else ranked_projection
    at_risk = watch_ranked[-1] if watch_ranked else None
    next_above = watch_ranked[-2] if len(watch_ranked) >= 2 else None
    watch_key = "current_week_points" if has_actual else "current_week_projected_points"

    gap_to_next = None
    if (
        at_risk
        and next_above
        and isinstance(at_risk.get(watch_key), (int, float))
        and isinstance(next_above.get(watch_key), (int, float))
    ):
        gap_to_next = round(
            float(next_above[watch_key]) - float(at_risk[watch_key]),
            4,
        )

    at_risk_assets = []
    if at_risk:
        candidates = sorted(
            [
                player for player in (at_risk.get("roster") or [])
                if player.get("position") not in {"D/ST", "K"}
            ],
            key=lambda player: float(player.get("projected_avg_points") or 0),
            reverse=True,
        )
        at_risk_assets = [
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "position": player.get("position"),
                "projected_avg_points": player.get("projected_avg_points"),
                "avg_points": player.get("avg_points"),
                "injury_status": player.get("injury_status"),
            }
            for player in candidates[:10]
        ]

    display_ranked = ranked_actual if has_actual else ranked_projection
    return {
        "mode": "all_play_knockout",
        "alive_team_count": len(alive),
        "eliminated_team_count": len(eliminated),
        "eliminated_teams": [
            {"team_id": team.get("team_id"), "name": team.get("name")}
            for team in eliminated
        ],
        "current_week_cutline_points": cutline,
        "projected_cutline_points": projected_cutline,
        "waterboys_margin_over_cutline": actual_margin,
        "waterboys_projected_margin_over_cutline": projected_margin,
        "elimination_watch": {
            "basis": basis,
            "team_id": at_risk.get("team_id") if at_risk else None,
            "name": at_risk.get("name") if at_risk else None,
            "points": at_risk.get("current_week_points") if at_risk else None,
            "projected_points": at_risk.get("current_week_projected_points") if at_risk else None,
            "gap_to_next_team": gap_to_next,
            "roster_release_watch": at_risk_assets,
        },
        "current_week_ranking": [
            {
                "rank": team.get("current_week_rank"),
                "team_id": team.get("team_id"),
                "name": team.get("name"),
                "points": team.get("current_week_points"),
                "projected_points": team.get("current_week_projected_points"),
                "projection_rank": team.get("current_week_projection_rank"),
            }
            for team in display_ranked
        ],
    }

def market_node(
    teams: list[dict],
    free_agents: list[dict],
    activity: list[dict],
) -> dict:
    positions = ("QB", "RB", "WR", "TE", "D/ST", "K")

    team_summaries = []
    for team in teams:
        roster = list(team.get("roster") or [])
        counts = {
            position: sum(1 for player in roster if player.get("position") == position)
            for position in positions
        }
        core = sorted(
            [
                player for player in roster
                if player.get("position") not in {"D/ST", "K"}
            ],
            key=lambda player: float(player.get("projected_avg_points") or 0),
            reverse=True,
        )[:6]
        team_summaries.append({
            "team_id": team.get("team_id"),
            "name": team.get("name"),
            "faab_remaining": team.get("acquisition_budget_remaining"),
            "waiver_rank": team.get("waiver_rank"),
            "trades": team.get("trades"),
            "position_counts": counts,
            "top_assets": [
                {
                    "player_id": player.get("player_id"),
                    "name": player.get("name"),
                    "position": player.get("position"),
                    "projected_avg_points": player.get("projected_avg_points"),
                    "avg_points": player.get("avg_points"),
                    "injury_status": player.get("injury_status"),
                }
                for player in core
            ],
        })

    free_agent_board = {}
    for position in positions:
        pool = [
            player for player in free_agents
            if player.get("position") == position
        ]
        pool.sort(
            key=lambda player: (
                bool(player.get("injured")),
                -(float(player.get("projected_avg_points") or 0)),
                -(float(player.get("percent_owned") or 0)),
            )
        )
        free_agent_board[position] = [
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "position": player.get("position"),
                "injury_status": player.get("injury_status"),
                "injured": player.get("injured"),
                "avg_points": player.get("avg_points"),
                "projected_avg_points": player.get("projected_avg_points"),
                "percent_owned": player.get("percent_owned"),
                "current_week_points": (player.get("current_week") or {}).get("points"),
                "current_week_projected_points": (player.get("current_week") or {}).get("projected_points"),
            }
            for player in pool[:15]
        ]

    successful_waiver_bids = []
    for row in activity:
        for action in row.get("actions") or []:
            if action.get("action") != "WAIVER ADDED":
                continue
            successful_waiver_bids.append({
                "date": row.get("date"),
                "team_id": action.get("team_id"),
                "team": action.get("team"),
                "player_id": action.get("player_id"),
                "player": action.get("player"),
                "bid": action.get("bid"),
            })
    successful_waiver_bids.sort(key=lambda row: int(row.get("date") or 0), reverse=True)

    budget_leaderboard = sorted(
        [
            {
                "team_id": team.get("team_id"),
                "name": team.get("name"),
                "remaining": team.get("acquisition_budget_remaining"),
                "spent": team.get("acquisition_budget_spent"),
            }
            for team in teams
            if team.get("roster_count", 0) > 0
        ],
        key=lambda row: (
            -(int(row.get("remaining") or 0)),
            int(row.get("spent") or 0),
        ),
    )

    return {
        "teams": team_summaries,
        "free_agent_board": free_agent_board,
        "successful_waiver_bids": successful_waiver_bids,
        "budget_leaderboard": budget_leaderboard,
    }

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
