from __future__ import annotations

from collections import Counter

FLEX = {"RB", "WR", "TE"}
HEALTH = {
    "ACTIVE": 1.0, "NORMAL": 1.0, "QUESTIONABLE": 0.85,
    "DAY_TO_DAY": 0.8, "DOUBTFUL": 0.45, "OUT": 0.2,
    "INJURY_RESERVE": 0.15,
}


def num(value):
    return float(value) if isinstance(value, (int, float)) else 0.0


def availability(player: dict) -> float:
    factor = HEALTH.get(str(player.get("injury_status") or "").upper(), 0.9)
    return min(factor, 0.85) if player.get("injured") is True else factor


def slot_counts(roster_cfg: dict) -> dict:
    raw = (roster_cfg or {}).get("slots") or {}
    return {
        "QB": int(raw.get("QB") or 0), "RB": int(raw.get("RB") or 0),
        "WR": int(raw.get("WR") or 0), "TE": int(raw.get("TE") or 0),
        "FLEX": int(raw.get("FLEX") or 0),
        "D/ST": int(raw.get("DST") or raw.get("D/ST") or 0),
        "K": int(raw.get("K") or 0),
    }


def optimize(players: list[dict], roster_cfg: dict) -> dict:
    counts = slot_counts(roster_cfg)
    by_pos = {}
    for player in players:
        by_pos.setdefault(str(player.get("position") or ""), []).append(player)
    for pool in by_pos.values():
        pool.sort(key=lambda p: num(p.get("projected_avg_points")), reverse=True)

    picked = []
    ids = set()
    for pos in ("QB", "RB", "WR", "TE", "D/ST", "K"):
        for player in by_pos.get(pos, [])[: counts.get(pos, 0)]:
            picked.append(player)
            ids.add(player.get("player_id"))

    flex = [
        p for p in players
        if p.get("position") in FLEX and p.get("player_id") not in ids
    ]
    flex.sort(key=lambda p: num(p.get("projected_avg_points")), reverse=True)
    for player in flex[: counts.get("FLEX", 0)]:
        picked.append(player)
        ids.add(player.get("player_id"))

    return {
        "projected_ppg": round(sum(num(p.get("projected_avg_points")) for p in picked), 4),
        "ids": ids,
        "players": [
            {"player_id": p.get("player_id"), "name": p.get("name"),
             "position": p.get("position"), "projected_avg_points": p.get("projected_avg_points")}
            for p in picked
        ],
    }


def replacement(candidate: dict, free_agents: list[dict]) -> tuple[float, str | None]:
    pool = [
        p for p in free_agents
        if p.get("position") == candidate.get("position")
        and p.get("player_id") != candidate.get("player_id")
    ]
    pool.sort(key=lambda p: num(p.get("projected_avg_points")), reverse=True)
    if not pool:
        return 0.0, None
    best = pool[0]
    return (
        round(num(candidate.get("projected_avg_points")) - num(best.get("projected_avg_points")), 4),
        best.get("name"),
    )


def suggest_drop(roster: list[dict], candidate: dict, lineup_ids: set, roster_cfg: dict) -> dict | None:
    counts = Counter(str(p.get("position") or "") for p in roster)
    starters = slot_counts(roster_cfg)
    limits = (roster_cfg or {}).get("position_limits") or {}
    candidate_pos = str(candidate.get("position") or "")
    limit_key = "DST" if candidate_pos == "D/ST" else candidate_pos
    hard_limit = limits.get(limit_key)
    forced_position = (
        candidate_pos
        if isinstance(hard_limit, int) and counts.get(candidate_pos, 0) >= hard_limit
        else None
    )

    choices = []
    for player in roster:
        if player.get("player_id") in lineup_ids:
            continue
        if forced_position and str(player.get("position") or "") != forced_position:
            continue
        pos = str(player.get("position") or "")
        need = float(starters.get(pos, 0))
        if pos in FLEX:
            need += starters.get("FLEX", 0) / 3.0
        redundancy = max(0.0, counts.get(pos, 0) - need)
        retention = num(player.get("projected_avg_points")) - 3.0 * redundancy
        choices.append((retention, num(player.get("projected_avg_points")), player))
    if not choices:
        return None
    player = sorted(choices, key=lambda row: (row[0], row[1]))[0][2]
    return {
        "player_id": player.get("player_id"), "name": player.get("name"),
        "position": player.get("position"),
        "projected_avg_points": player.get("projected_avg_points"),
    }


def bid_range(candidate: dict, source: str, risk_delta: float, scarcity: float, budget: int) -> dict:
    if source == "trade":
        return {"applicable": False, "reason": "Gross trade value; outgoing cost not included."}
    share = (
        0.01 + 0.014 * max(0.0, risk_delta)
        + 0.0045 * max(0.0, scarcity)
        + 0.0015 * max(0.0, num(candidate.get("projected_avg_points")))
    )
    if risk_delta < 0.5:
        share = min(share, 0.04)
    share *= 1.0 if source == "elimination_watch" else 0.75
    share = min(0.50, max(0.0, share))
    mid = int(round(budget * share))
    return {
        "applicable": True, "low": int(round(mid * 0.70)),
        "midpoint": mid, "high": min(budget, int(round(mid * 1.15))),
        "budget_share_midpoint": round(share, 4), "advisory_only": True,
    }


def score_candidate(candidate: dict, source: str, waterboys: dict, free_agents: list[dict],
                    roster_cfg: dict, weeks: int, budget: int, source_team: dict | None = None) -> dict:
    roster = list(waterboys.get("roster") or [])
    base = optimize(roster, roster_cfg)
    new = optimize(roster + [candidate], roster_cfg)
    delta = round(new["projected_ppg"] - base["projected_ppg"], 4)
    health = availability(candidate)
    risk = round(delta * health, 4)
    scarcity, replacement_name = replacement(candidate, free_agents)
    result = {
        "player_id": candidate.get("player_id"), "name": candidate.get("name"),
        "position": candidate.get("position"), "source_type": source,
        "source_team_id": source_team.get("team_id") if source_team else None,
        "source_team": source_team.get("name") if source_team else None,
        "inputs": {
            "projected_avg_points": candidate.get("projected_avg_points"),
            "avg_points": candidate.get("avg_points"),
            "injury_status": candidate.get("injury_status"),
            "availability_factor": health,
        },
        "value": {
            "marginal_lineup_ppg": delta,
            "risk_adjusted_marginal_ppg": risk,
            "expected_added_points_remaining": round(risk * weeks, 2),
            "value_over_best_free_replacement_ppg": scarcity,
            "best_free_replacement": replacement_name,
            "immediate_starter": candidate.get("player_id") in new["ids"],
        },
        "suggested_drop": suggest_drop(roster, candidate, new["ids"], roster_cfg),
        "faab_reference": bid_range(candidate, source, risk, scarcity, budget),
    }
    bid = result["faab_reference"]
    if bid.get("applicable") and int(bid.get("midpoint") or 0) > 0:
        midpoint = int(bid["midpoint"])
        result["cost_efficiency"] = {
            "risk_adjusted_ppg_per_100_faab_at_midpoint": round(risk * 100 / midpoint, 3),
            "remaining_points_per_100_faab_at_midpoint": round(
                result["value"]["expected_added_points_remaining"] * 100 / midpoint, 2
            ),
        }
    else:
        result["cost_efficiency"] = None
    return result


def build_value_engine(waterboys: dict, teams: list[dict], free_agents: list[dict],
                       survival: dict, league_cfg: dict, settings: dict) -> dict:
    roster_cfg = league_cfg.get("roster") or {}
    current_week = int(league_cfg.get("current_week") or 0)
    weeks = max(0, int(settings.get("regular_season_count") or current_week) - current_week)
    budget = int(waterboys.get("acquisition_budget_remaining") or
                 (league_cfg.get("waivers") or {}).get("faab_start") or 0)

    waivers = [
        score_candidate(p, "free_agent", waterboys, free_agents, roster_cfg, weeks, budget)
        for p in free_agents if p.get("position") in {"QB", "RB", "WR", "TE", "D/ST", "K"}
    ]

    risk_id = (survival.get("elimination_watch") or {}).get("team_id")
    risk_team = next((t for t in teams if t.get("team_id") == risk_id), None)
    releases = []
    if risk_team:
        releases = [
            score_candidate(p, "elimination_watch", waterboys, free_agents, roster_cfg,
                            weeks, budget, risk_team)
            for p in risk_team.get("roster") or []
            if p.get("position") in {"QB", "RB", "WR", "TE", "D/ST", "K"}
        ]

    trades = []
    for team in teams:
        if team.get("team_id") in {waterboys.get("team_id"), risk_id} or int(team.get("roster_count") or 0) <= 0:
            continue
        trades.extend(
            score_candidate(p, "trade", waterboys, free_agents, roster_cfg, weeks, budget, team)
            for p in team.get("roster") or []
            if p.get("position") in {"QB", "RB", "WR", "TE"}
        )

    key = lambda row: (
        num(row["value"]["risk_adjusted_marginal_ppg"]),
        num(row["value"]["value_over_best_free_replacement_ppg"]),
    )
    waivers.sort(key=key, reverse=True)
    releases.sort(key=key, reverse=True)
    trades.sort(key=key, reverse=True)
    base = optimize(list(waterboys.get("roster") or []), roster_cfg)

    return {
        "schema": "waterboys.value_engine.v1", "status": "advisory",
        "methodology": {
            "basis": "ESPN projected average points under this league scoring.",
            "marginal_lineup_ppg": "Optimized WaterBoys lineup with candidate minus current optimized lineup.",
            "replacement_value": "Candidate projection minus best free alternative at the same position.",
            "health_factors": HEALTH,
            "faab_reference": "Advisory heuristic, not an execution rule.",
            "trade_targets": "Gross acquisition value; outgoing-player cost is not included.",
        },
        "waterboys_baseline": {
            "optimized_lineup_projected_ppg": base["projected_ppg"],
            "optimized_lineup": base["players"], "faab_remaining": budget,
            "weeks_remaining": weeks,
        },
        "waiver_targets": waivers[:75],
        "elimination_watch_targets": releases[:25],
        "trade_targets": trades[:75],
    }
