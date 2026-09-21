from __future__ import annotations

from espn_api.football import League

from .normalize import activity_node, box_score_node, player_node, team_node, utc_now


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

    teams = [team_node(team) for team in list(league.teams)]
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

    current_week = getattr(league, "current_week", None)
    try:
        matchups = [box_score_node(box) for box in league.box_scores()]
    except Exception:
        matchups = []

    try:
        free_agents = [player_node(player) for player in league.free_agents(size=500)]
    except Exception:
        free_agents = []

    try:
        activity = [activity_node(row) for row in league.recent_activity(size=100)]
    except Exception:
        activity = []

    if int(league_cfg.get("league_size") or 0) and len(teams) != int(league_cfg["league_size"]):
        raise RuntimeError(
            f"league team count mismatch: expected {league_cfg['league_size']}, got {len(teams)}"
        )

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
            "format": league_cfg.get("format"),
            "roster": league_cfg.get("roster"),
            "waivers": league_cfg.get("waivers"),
        },
        "waterboys": waterboys,
        "teams": teams,
        "matchups": matchups,
        "free_agents": free_agents,
        "activity": activity,
        "privacy": {
            "credentials_included": False,
            "tokens_included": False,
            "cookies_included": False,
        },
    }
