from __future__ import annotations

from typing import Any

from .value import FLEX, availability, num, score_candidate, slot_counts


STARTER_SLOTS = {"QB", "RB", "WR", "TE", "RB/WR/TE", "FLEX", "D/ST", "K"}


def weekly_projection(player: dict) -> float:
    return num((player.get("current_week") or {}).get("projected_points"))


def optimize_weekly(players: list[dict], roster_cfg: dict, *, risk_adjusted: bool = False) -> dict:
    counts = slot_counts(roster_cfg)

    def score(player: dict) -> float:
        projection = weekly_projection(player)
        return projection * availability(player) if risk_adjusted else projection

    by_pos: dict[str, list[dict]] = {}
    for player in players:
        by_pos.setdefault(str(player.get("position") or ""), []).append(player)
    for pool in by_pos.values():
        pool.sort(key=score, reverse=True)

    picked: list[tuple[dict, str]] = []
    ids: set[Any] = set()
    for pos in ("QB", "RB", "WR", "TE", "D/ST", "K"):
        for player in by_pos.get(pos, [])[: counts.get(pos, 0)]:
            picked.append((player, pos))
            ids.add(player.get("player_id"))

    flex = [
        player for player in players
        if player.get("position") in FLEX and player.get("player_id") not in ids
    ]
    flex.sort(key=score, reverse=True)
    for player in flex[: counts.get("FLEX", 0)]:
        picked.append((player, "RB/WR/TE"))
        ids.add(player.get("player_id"))

    raw = sum(weekly_projection(player) for player, _ in picked)
    risk = sum(weekly_projection(player) * availability(player) for player, _ in picked)
    return {
        "projected_points": round(raw, 4),
        "risk_adjusted_projected_points": round(risk, 4),
        "ids": ids,
        "players": [
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "position": player.get("position"),
                "assigned_slot": slot,
                "injury_status": player.get("injury_status"),
                "projected_points": weekly_projection(player),
                "risk_adjusted_projected_points": round(
                    weekly_projection(player) * availability(player), 4
                ),
            }
            for player, slot in picked
        ],
    }


def projected_rank(points: float, survival: dict, waterboys_team_id: int | None) -> int | None:
    rows = list(survival.get("current_week_ranking") or [])
    if not rows:
        return None
    simulated = []
    for row in rows:
        team_id = row.get("team_id")
        projection = points if team_id == waterboys_team_id else row.get("projected_points")
        if isinstance(projection, (int, float)):
            simulated.append((float(projection), team_id))
    simulated.sort(key=lambda row: (-row[0], str(row[1])))
    for index, (_, team_id) in enumerate(simulated, start=1):
        if team_id == waterboys_team_id:
            return index
    return None


def _team_lookup(teams: list[dict]) -> dict:
    return {team.get("team_id"): team for team in teams}


def _player_lookup(teams: list[dict], free_agents: list[dict]) -> dict:
    result = {}
    for team in teams:
        for player in team.get("roster") or []:
            result[player.get("player_id")] = player
    for player in free_agents:
        result[player.get("player_id")] = player
    return result


def _release_assets(team: dict | None, limit: int = 8) -> list[dict]:
    if not team:
        return []
    pool = [
        player for player in (team.get("roster") or [])
        if player.get("position") not in {"D/ST", "K"}
    ]
    pool.sort(key=lambda player: num(player.get("projected_avg_points")), reverse=True)
    return [
        {
            "player_id": player.get("player_id"),
            "name": player.get("name"),
            "position": player.get("position"),
            "projected_avg_points": player.get("projected_avg_points"),
            "avg_points": player.get("avg_points"),
            "injury_status": player.get("injury_status"),
        }
        for player in pool[:limit]
    ]


def elimination_race(teams: list[dict], survival: dict, *, danger_points: float = 25.0) -> list[dict]:
    cutline = survival.get("projected_cutline_points")
    team_by_id = _team_lookup(teams)
    rows = []
    for row in survival.get("current_week_ranking") or []:
        projected = row.get("projected_points")
        if not isinstance(projected, (int, float)):
            continue
        if isinstance(cutline, (int, float)) and float(projected) > float(cutline) + danger_points:
            continue
        team = team_by_id.get(row.get("team_id"))
        rows.append({
            "projection_rank": row.get("projection_rank"),
            "team_id": row.get("team_id"),
            "name": row.get("name"),
            "projected_points": projected,
            "gap_over_projected_cutline": (
                round(float(projected) - float(cutline), 4)
                if isinstance(cutline, (int, float)) else None
            ),
            "faab_remaining": (team or {}).get("acquisition_budget_remaining"),
            "roster_release_watch": _release_assets(team),
        })
    rows.sort(key=lambda row: (
        num(row.get("projected_points")),
        -(int(row.get("projection_rank") or 0)),
    ))
    return rows


def _lineup_changes(roster: list[dict], optimized: dict) -> dict:
    current = {
        player.get("player_id"): str(player.get("lineup_slot") or "")
        for player in roster
        if str(player.get("lineup_slot") or "") in STARTER_SLOTS
    }
    target = {
        player.get("player_id"): player.get("assigned_slot")
        for player in optimized.get("players") or []
    }
    roster_by_id = {player.get("player_id"): player for player in roster}
    starts = []
    benches = []
    for player_id, slot in target.items():
        if player_id not in current:
            player = roster_by_id.get(player_id) or {}
            starts.append({
                "player_id": player_id,
                "name": player.get("name"),
                "position": player.get("position"),
                "to_slot": slot,
                "projected_points": weekly_projection(player),
            })
    for player_id, slot in current.items():
        if player_id not in target:
            player = roster_by_id.get(player_id) or {}
            benches.append({
                "player_id": player_id,
                "name": player.get("name"),
                "position": player.get("position"),
                "from_slot": slot,
                "projected_points": weekly_projection(player),
            })
    return {"start": starts, "bench": benches}


def _decorate_target(
    row: dict,
    player: dict | None,
    waterboys: dict,
    survival: dict,
    roster_cfg: dict,
    base_weekly_raw: dict,
    base_weekly_risk: dict,
    current_points: float,
    current_rank: int | None,
    acquisition_path: str,
) -> dict:
    weekly_delta = 0.0
    risk_weekly_delta = 0.0
    post_points = current_points
    post_rank = current_rank
    if player:
        after_raw = optimize_weekly(
            list(waterboys.get("roster") or []) + [player],
            roster_cfg,
            risk_adjusted=False,
        )
        after_risk = optimize_weekly(
            list(waterboys.get("roster") or []) + [player],
            roster_cfg,
            risk_adjusted=True,
        )
        weekly_delta = round(
            num(after_raw.get("projected_points")) - num(base_weekly_raw.get("projected_points")),
            4,
        )
        risk_weekly_delta = round(
            num(after_risk.get("risk_adjusted_projected_points"))
            - num(base_weekly_risk.get("risk_adjusted_projected_points")),
            4,
        )
        post_points = round(current_points + risk_weekly_delta, 4)
        post_rank = projected_rank(post_points, survival, waterboys.get("team_id"))

    durable_ppg = num((row.get("value") or {}).get("risk_adjusted_marginal_ppg"))
    rank_gain = (
        int(current_rank) - int(post_rank)
        if isinstance(current_rank, int) and isinstance(post_rank, int)
        else 0
    )
    if rank_gain >= 3 or durable_ppg >= 8:
        move_class = "launch"
    elif rank_gain >= 1 or durable_ppg >= 3:
        move_class = "material"
    else:
        move_class = "maintenance"

    return {
        "player_id": row.get("player_id"),
        "name": row.get("name"),
        "position": row.get("position"),
        "acquisition_path": acquisition_path,
        "source_team_id": row.get("source_team_id"),
        "source_team": row.get("source_team"),
        "injury_status": (row.get("inputs") or {}).get("injury_status"),
        "availability_status": (row.get("inputs") or {}).get("availability_status"),
        "durable_risk_adjusted_marginal_ppg": durable_ppg,
        "expected_added_points_remaining": (row.get("value") or {}).get(
            "expected_added_points_remaining"
        ),
        "current_week_marginal_points": weekly_delta,
        "risk_adjusted_current_week_marginal_points": risk_weekly_delta,
        "estimated_post_move_projected_points": post_points,
        "estimated_post_move_projection_rank": post_rank,
        "estimated_rank_gain": rank_gain,
        "move_class": move_class,
        "suggested_drop": row.get("suggested_drop"),
        "bid_guidance": row.get("bid_guidance"),
        "faab_reference": row.get("faab_reference"),
        "trade_cost_status": (
            "gross_only_outgoing_cost_not_modeled"
            if acquisition_path == "trade" else "not_applicable"
        ),
    }


def build_placement_engine(
    waterboys: dict,
    teams: list[dict],
    free_agents: list[dict],
    survival: dict,
    league_cfg: dict,
    settings: dict,
    value_engine: dict,
    market: dict | None = None,
    waiver_offers: list[dict] | None = None,
) -> dict:
    roster_cfg = league_cfg.get("roster") or {}
    roster = list(waterboys.get("roster") or [])
    current_points = num(waterboys.get("current_week_projected_points"))
    current_rank = waterboys.get("current_week_projection_rank")
    base_weekly = optimize_weekly(roster, roster_cfg, risk_adjusted=False)
    base_weekly_risk = optimize_weekly(roster, roster_cfg, risk_adjusted=True)
    optimized_rank = projected_rank(
        num(base_weekly.get("projected_points")),
        survival,
        waterboys.get("team_id"),
    )
    risk_rank = projected_rank(
        num(base_weekly_risk.get("risk_adjusted_projected_points")),
        survival,
        waterboys.get("team_id"),
    )

    race = elimination_race(teams, survival)
    race_ids = {
        row.get("team_id") for row in race
        if row.get("team_id") != waterboys.get("team_id")
    }

    current_week = int(league_cfg.get("current_week") or 0)
    weeks = max(0, int(settings.get("regular_season_count") or current_week) - current_week)
    budget = int(
        waterboys.get("acquisition_budget_remaining")
        or (league_cfg.get("waivers") or {}).get("faab_start")
        or 0
    )

    future_release_rows = []
    for team in teams:
        if team.get("team_id") not in race_ids:
            continue
        for player in team.get("roster") or []:
            if player.get("position") not in {"QB", "RB", "WR", "TE", "D/ST", "K"}:
                continue
            future_release_rows.append(
                score_candidate(
                    player,
                    "elimination_race",
                    waterboys,
                    free_agents,
                    roster_cfg,
                    weeks,
                    budget,
                    team,
                    market=market,
                    waiver_offers=waiver_offers,
                )
            )
    future_release_rows.sort(
        key=lambda row: (
            num((row.get("value") or {}).get("risk_adjusted_marginal_ppg")),
            num((row.get("value") or {}).get("expected_added_points_remaining")),
        ),
        reverse=True,
    )

    player_by_id = _player_lookup(teams, free_agents)
    board = []
    seen = set()

    for row in value_engine.get("waiver_targets") or []:
        key = ("waiver", row.get("player_id"))
        if key in seen:
            continue
        seen.add(key)
        board.append(_decorate_target(
            row,
            player_by_id.get(row.get("player_id")),
            waterboys,
            survival,
            roster_cfg,
            base_weekly,
            base_weekly_risk,
            current_points,
            current_rank,
            "waiver",
        ))

    for row in future_release_rows:
        key = ("future_elimination", row.get("player_id"))
        if key in seen:
            continue
        seen.add(key)
        board.append(_decorate_target(
            row,
            player_by_id.get(row.get("player_id")),
            waterboys,
            survival,
            roster_cfg,
            base_weekly,
            base_weekly_risk,
            current_points,
            current_rank,
            "future_elimination",
        ))

    for row in value_engine.get("trade_targets") or []:
        key = ("trade", row.get("player_id"))
        if key in seen:
            continue
        seen.add(key)
        board.append(_decorate_target(
            row,
            player_by_id.get(row.get("player_id")),
            waterboys,
            survival,
            roster_cfg,
            base_weekly,
            base_weekly_risk,
            current_points,
            current_rank,
            "trade",
        ))

    weekly_board = sorted(
        board,
        key=lambda row: (
            int(row.get("estimated_rank_gain") or 0),
            num(row.get("risk_adjusted_current_week_marginal_points")),
            num(row.get("durable_risk_adjusted_marginal_ppg")),
        ),
        reverse=True,
    )
    durable_board = sorted(
        board,
        key=lambda row: (
            num(row.get("durable_risk_adjusted_marginal_ppg")),
            num(row.get("expected_added_points_remaining")),
            int(row.get("estimated_rank_gain") or 0),
        ),
        reverse=True,
    )
    class_weight = {"launch": 2, "material": 1, "maintenance": 0}
    board.sort(
        key=lambda row: (
            class_weight.get(str(row.get("move_class") or ""), 0),
            num(row.get("durable_risk_adjusted_marginal_ppg"))
            + 0.75 * int(row.get("estimated_rank_gain") or 0),
            int(row.get("estimated_rank_gain") or 0),
            num(row.get("risk_adjusted_current_week_marginal_points")),
        ),
        reverse=True,
    )

    cutline = survival.get("projected_cutline_points")
    margin = (
        round(current_points - float(cutline), 4)
        if isinstance(cutline, (int, float)) else None
    )
    alive = int(survival.get("alive_team_count") or 0)
    if (
        isinstance(current_rank, int)
        and alive
        and current_rank >= alive - 1
    ) or (isinstance(margin, (int, float)) and margin < 5):
        pressure = "red"
    elif (
        isinstance(current_rank, int)
        and alive
        and current_rank >= alive - 4
    ) or (isinstance(margin, (int, float)) and margin < 15):
        pressure = "yellow"
    else:
        pressure = "green"

    return {
        "schema": "waterboys.placement_engine.v1",
        "status": "advisory",
        "survival_pressure": pressure,
        "current": {
            "projected_points": current_points,
            "projection_rank": current_rank,
            "alive_team_count": alive,
            "projected_cutline_points": cutline,
            "margin_over_projected_cutline": margin,
        },
        "lineup_optimizer": {
            "current_lineup_projected_points": current_points,
            "optimized_weekly_projected_points": base_weekly.get("projected_points"),
            "optimized_weekly_projection_rank": optimized_rank,
            "risk_adjusted_optimized_projected_points": base_weekly_risk.get(
                "risk_adjusted_projected_points"
            ),
            "risk_adjusted_projection_rank": risk_rank,
            "projected_lineup_leakage": round(
                num(base_weekly.get("projected_points")) - current_points, 4
            ),
            "recommended_changes": _lineup_changes(roster, base_weekly),
            "optimized_lineup": base_weekly.get("players"),
        },
        "elimination_race": race,
        "future_elimination_targets": future_release_rows[:50],
        "best_acquisitions": board[:50],
        "weekly_rank_up_targets": weekly_board[:30],
        "durable_rank_up_targets": durable_board[:30],
        "methodology": {
            "weekly_rank": (
                "Simulates WaterBoys against current ESPN team projections while holding "
                "other teams constant."
            ),
            "future_elimination": (
                "Scores assets on every team within 25 projected points of the current "
                "elimination cutline, not only the single last-place team."
            ),
            "rank_after_move": (
                "Uses risk-adjusted current-week marginal lineup points where player weekly "
                "projections are available. Trade rows remain gross because outgoing trade "
                "cost is not modeled."
            ),
            "boards": (
                "best_acquisitions blends durable value with immediate rank gain; "
                "weekly_rank_up_targets prioritizes this week's placement; "
                "durable_rank_up_targets preserves season-long launch targets even when "
                "a current-week projection is missing or suppressed."
            ),
        },
    }
