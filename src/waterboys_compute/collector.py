from __future__ import annotations

from espn_api.football import League

from .normalize import (
    activity_node,
    player_node,
    settings_node,
    survival_node,
    team_node,
    utc_now,
)


def build_league(runtime: dict) -> League:
    league_cfg = runtime["league"]
    league_id = int(league_cfg.get("league_id") or 0)
    season = int(league_cfg.get("season") or 0)
    if league_id <= 0 or season <= 0 or league_cfg.get("ready") is not True:
        raise RuntimeError("private league configuration is not ready")
    espn_s2 = str(runtime.get("espn_s2") or "")
    swid = str(runtime.get("swid") or "")
    if not espn_s2 or not swid:
        raise RuntimeError("ESPN runtime credentials are unavailable")
    return League(league_id=league_id, year=season, espn_s2=espn_s2, swid=swid)


def collect_snapshot(runtime: dict) -> dict:
    league_cfg = runtime["league"]
    league = build_league(runtime)
    current_week = getattr(league, "current_week", None)
    nfl_week = getattr(league, "nfl_week", None)

    league_settings = settings_node(league.settings)
    acquisition_budget = league_settings.get("acquisition_budget")
    if not isinstance(acquisition_budget, int):
        configured = (league_cfg.get("waivers") or {}).get("faab_start")
        acquisition_budget = int(configured) if isinstance(configured, int) else None

    teams = [
        team_node(
            team,
            current_week=current_week,
            acquisition_budget=acquisition_budget,
        )
        for team in list(league.teams)
    ]

    configured_team_id = league_cfg.get("team_id")
    configured_name = str(league_cfg.get("team_name") or "").strip().casefold()

    waterboys = None
    for team in teams:
        if configured_team_id is not None and team.get("team_id") == configured_team_id:
            waterboys = team
            break
        if str(team.get("name") or "").strip().casefold() == configured_name:
            waterboys = team
            break
    if waterboys is None:
        raise RuntimeError("WaterBoys team could not be resolved from authenticated league state")

    try:
        free_agents = [
            player_node(player, current_week=current_week)
            for player in league.free_agents(size=500)
        ]
    except Exception:
        free_agents = []

    try:
        activity = [
            activity_node(row)
            for row in league.recent_activity(size=500)
        ]
    except Exception:
        activity = []

    expected = int(league_cfg.get("league_size") or 0)
    if expected and len(teams) != expected:
        raise RuntimeError(
            f"league team count mismatch: expected {expected}, got {len(teams)}"
        )

    survival = survival_node(teams, waterboys.get("team_id"))

    return {
        "schema": "waterboys.snapshot.v1",
        "status": "ok",
        "collected_at": utc_now(),
        "season": int(league_cfg["season"]),
        "league": {
            "league_id": int(league_cfg["league_id"]),
            "league_name": league_cfg.get("league_name"),
            "team_name": league_cfg.get("team_name"),
            "league_size": league_cfg.get("league_size"),
            "current_week": current_week,
            "nfl_week": nfl_week,
            "format": {
                **(league_cfg.get("format") or {}),
                "all_play": True,
            },
            "roster": league_cfg.get("roster"),
            "waivers": league_cfg.get("waivers"),
            "settings": league_settings,
        },
        "waterboys": waterboys,
        "teams": teams,
        "survival": survival,
        "free_agents": free_agents,
        "activity": activity,
        "capabilities": {
            "all_teams": len(teams) == expected if expected else bool(teams),
            "all_team_rosters": all(
                team.get("roster_count", 0) > 0
                or any(
                    e.get("team_id") == team.get("team_id")
                    for e in survival.get("eliminated_teams", [])
                )
                for team in teams
            ),
            "free_agents": bool(free_agents),
            "activity": bool(activity),
            "faab": acquisition_budget is not None,
            "trade_settings": league_settings.get("trade_deadline") is not None,
            "weekly_player_stats": True,
            "player_schedule": True,
            "survival_state": True,
        },
        "privacy": {
            "credentials_included": False,
            "tokens_included": False,
            "cookies_included": False,
        },
    }
