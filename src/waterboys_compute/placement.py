from __future__ import annotations

from typing import Any

from .value import FLEX, availability, num, optimize as optimize_durable, score_candidate, slot_counts


STARTER_SLOTS = {"QB", "RB", "WR", "TE", "RB/WR/TE", "FLEX", "D/ST", "K"}
BLOCKED_START_STATUSES = {
    "OUT",
    "INJURY_RESERVE",
    "DOUBTFUL",
    "SUSPENDED",
    "SUSPENSION",
    "PUP",
    "COMMISSIONER_EXEMPT",
}


def _lineup_slot(player: dict) -> str:
    return str(player.get("lineup_slot") or "").upper()


def _injury_status(player: dict) -> str:
    return str(player.get("injury_status") or "").upper()


def _game_locked(player: dict) -> bool:
    return isinstance((player.get("current_week") or {}).get("points"), (int, float))


def starter_eligible(player: dict) -> bool:
    slot = _lineup_slot(player)
    current_week = player.get("current_week") or {}
    projection = num(current_week.get("projected_points"))
    has_game = bool(current_week.get("opponent") or current_week.get("date"))

    if slot == "IR" or _injury_status(player) in BLOCKED_START_STATUSES:
        return False
    if _game_locked(player) and slot not in STARTER_SLOTS:
        return False
    if projection <= 0 and not has_game and not _game_locked(player):
        return False
    return True


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

    picked: list[tuple[dict, str]] = []
    ids: set[Any] = set()
    starter_holes: list[dict] = []

    def record_hole(player: dict | None, slot: str, reason: str) -> None:
        starter_holes.append({
            "player_id": player.get("player_id") if player else None,
            "name": player.get("name") if player else None,
            "position": player.get("position") if player else (
                "D/ST" if slot == "D/ST" else slot
            ),
            "slot": slot,
            "injury_status": player.get("injury_status") if player else None,
            "projected_points": weekly_projection(player or {}),
            "game_locked": _game_locked(player or {}),
            "reason": reason,
        })

    def add(player: dict, slot: str) -> None:
        picked.append((player, slot))
        ids.add(player.get("player_id"))

    def fill_position(pos: str) -> None:
        need = int(counts.get(pos, 0))
        if need <= 0:
            return

        pool = list(by_pos.get(pos, []))
        current_locked = [
            player for player in pool
            if _lineup_slot(player) == pos and _game_locked(player)
        ]
        for player in current_locked[:need]:
            if player.get("player_id") in ids:
                continue
            add(player, pos)
            if not starter_eligible(player):
                record_hole(player, pos, "locked_nonstartable_starter")

        remaining = need - sum(1 for _, slot in picked if slot == pos)
        if remaining > 0:
            eligible = [
                player for player in pool
                if player.get("player_id") not in ids
                and not _game_locked(player)
                and starter_eligible(player)
            ]
            eligible.sort(key=score, reverse=True)
            for player in eligible[:remaining]:
                add(player, pos)

        remaining = need - sum(1 for _, slot in picked if slot == pos)
        if remaining > 0:
            current_fallback = [
                player for player in pool
                if player.get("player_id") not in ids
                and _lineup_slot(player) == pos
            ]
            current_fallback.sort(key=score, reverse=True)
            for player in current_fallback[:remaining]:
                add(player, pos)
                record_hole(player, pos, "nonstartable_starter_no_healthy_replacement")

        remaining = need - sum(1 for _, slot in picked if slot == pos)
        for _ in range(max(0, remaining)):
            record_hole(None, pos, "unfilled_starter_slot")

    for pos in ("QB", "RB", "WR", "TE", "D/ST", "K"):
        fill_position(pos)

    flex_need = int(counts.get("FLEX", 0))
    flex_slots = {"RB/WR/TE", "FLEX"}
    current_locked_flex = [
        player for player in players
        if player.get("position") in FLEX
        and player.get("player_id") not in ids
        and _lineup_slot(player) in flex_slots
        and _game_locked(player)
    ]
    for player in current_locked_flex[:flex_need]:
        add(player, "RB/WR/TE")
        if not starter_eligible(player):
            record_hole(player, "RB/WR/TE", "locked_nonstartable_starter")

    flex_remaining = flex_need - sum(1 for _, slot in picked if slot == "RB/WR/TE")
    if flex_remaining > 0:
        flex = [
            player for player in players
            if player.get("position") in FLEX
            and player.get("player_id") not in ids
            and not _game_locked(player)
            and starter_eligible(player)
        ]
        flex.sort(key=score, reverse=True)
        for player in flex[:flex_remaining]:
            add(player, "RB/WR/TE")

    flex_remaining = flex_need - sum(1 for _, slot in picked if slot == "RB/WR/TE")
    if flex_remaining > 0:
        current_fallback = [
            player for player in players
            if player.get("position") in FLEX
            and player.get("player_id") not in ids
            and _lineup_slot(player) in flex_slots
        ]
        current_fallback.sort(key=score, reverse=True)
        for player in current_fallback[:flex_remaining]:
            add(player, "RB/WR/TE")
            record_hole(
                player,
                "RB/WR/TE",
                "nonstartable_starter_no_healthy_replacement",
            )

    flex_remaining = flex_need - sum(1 for _, slot in picked if slot == "RB/WR/TE")
    for _ in range(max(0, flex_remaining)):
        record_hole(None, "RB/WR/TE", "unfilled_starter_slot")

    raw = sum(weekly_projection(player) for player, _ in picked)
    risk = sum(weekly_projection(player) * availability(player) for player, _ in picked)
    return {
        "projected_points": round(raw, 4),
        "risk_adjusted_projected_points": round(risk, 4),
        "ids": ids,
        "starter_holes": starter_holes,
        "players": [
            {
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "position": player.get("position"),
                "assigned_slot": slot,
                "injury_status": player.get("injury_status"),
                "starter_eligible": starter_eligible(player),
                "game_locked": _game_locked(player),
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


def _slot_accepts(position: str, slot: str) -> bool:
    normalized = "RB/WR/TE" if slot == "FLEX" else slot
    if normalized == position:
        return True
    return normalized == "RB/WR/TE" and position in FLEX


def _lineup_changes(roster: list[dict], optimized: dict) -> dict:
    roster_by_id = {p.get("player_id"): p for p in roster}
    current = {
        p.get("player_id"): str(p.get("lineup_slot") or "")
        for p in roster
        if str(p.get("lineup_slot") or "") in STARTER_SLOTS
    }
    target_rows = {
        p.get("player_id"): p for p in (optimized.get("players") or [])
    }
    target = {
        pid: str(row.get("assigned_slot") or "")
        for pid, row in target_rows.items()
    }

    detail = []
    starts, benches, reassign = [], [], []

    def add(pid, from_slot, to_slot, kind):
        p = roster_by_id.get(pid) or {}
        row = {
            "player_id": pid,
            "name": p.get("name"),
            "position": p.get("position"),
            "from_slot": from_slot,
            "to_slot": to_slot,
            "projected_points": weekly_projection(p),
            "kind": kind,
        }
        detail.append(row)
        {"start": starts, "bench": benches, "reassign": reassign}[kind].append(dict(row))

    for pid, from_slot in current.items():
        to_slot = target.get(pid)
        if to_slot is None:
            add(pid, from_slot, "BE", "bench")
        elif to_slot != from_slot:
            add(pid, from_slot, to_slot, "reassign")

    for pid, to_slot in target.items():
        if pid in current:
            continue
        p = roster_by_id.get(pid) or {}
        add(pid, str(p.get("lineup_slot") or "BE"), to_slot, "start")

    components = []
    for row in detail:
        slots = {
            s for s in (row["from_slot"], row["to_slot"])
            if s in STARTER_SLOTS
        }
        overlaps = [
            i for i, comp in enumerate(components)
            if slots & comp["slots"]
        ]
        if not overlaps:
            components.append({"slots": set(slots), "rows": [row]})
            continue
        base = overlaps[0]
        components[base]["slots"].update(slots)
        components[base]["rows"].append(row)
        for i in reversed(overlaps[1:]):
            components[base]["slots"].update(components[i]["slots"])
            components[base]["rows"].extend(components[i]["rows"])
            components.pop(i)

    packed = []
    locked_all = []
    for i, comp in enumerate(components, 1):
        pids = {row["player_id"] for row in comp["rows"]}
        locked = sorted(
            pid for pid in pids
            if isinstance(
                ((roster_by_id.get(pid) or {}).get("current_week") or {}).get("points"),
                (int, float),
            )
        )
        locked_all.extend(locked)
        dates = [
            str(((roster_by_id.get(pid) or {}).get("current_week") or {}).get("date"))
            for pid in pids
            if ((roster_by_id.get(pid) or {}).get("current_week") or {}).get("date")
        ]
        gain = round(
            sum(row["projected_points"] for row in comp["rows"] if row["kind"] == "start")
            - sum(row["projected_points"] for row in comp["rows"] if row["kind"] == "bench"),
            4,
        )
        packed.append({
            "component_id": i,
            "slots": sorted(comp["slots"]),
            "moves": [
                {
                    "player_id": int(row["player_id"]),
                    "from_slot": str(row["from_slot"]),
                    "to_slot": str(row["to_slot"]),
                }
                for row in comp["rows"]
            ],
            "player_ids": sorted(pids),
            "game_locked_player_ids": locked,
            "kickoff": min(dates) if dates else "9999-12-31 23:59:59",
            "projected_gain": gain,
            "auto_executable": bool(comp["rows"]) and not locked,
        })

    packed.sort(key=lambda x: (
        str(x.get("kickoff") or "9999-12-31 23:59:59"),
        -num(x.get("projected_gain")),
        int(x.get("component_id") or 0),
    ))

    return {
        "start": starts,
        "bench": benches,
        "reassign": reassign,
        "moves": [
            {
                "player_id": int(row["player_id"]),
                "from_slot": str(row["from_slot"]),
                "to_slot": str(row["to_slot"]),
            }
            for row in detail
        ],
        "components": packed,
        "game_locked_player_ids": sorted(set(locked_all)),
        "auto_executable": any(x.get("auto_executable") is True for x in packed),
    }


def commands_for_lineup_repair(snapshot: dict) -> list[dict]:
    placement = snapshot.get("placement_engine") or {}
    optimizer = placement.get("lineup_optimizer") or {}
    changes = optimizer.get("recommended_changes") or {}
    if changes.get("auto_executable") is not True:
        return []

    starts = list(changes.get("start") or [])
    benches = list(changes.get("bench") or [])
    if not starts or not benches:
        command = command_for_lineup_repair(snapshot)
        return [command] if command else []

    roster = list((snapshot.get("waterboys") or {}).get("roster") or [])
    roster_by_id = {player.get("player_id"): player for player in roster}
    remaining_benches = list(benches)
    commands = []
    stamp = str(snapshot.get("collected_at") or "unknown").replace(":", "").replace("-", "").replace(".", "")

    for index, start in enumerate(starts):
        to_slot = str(start.get("to_slot") or "")
        match_index = next(
            (
                idx for idx, bench in enumerate(remaining_benches)
                if str(bench.get("from_slot") or "") == to_slot
            ),
            None,
        )
        if match_index is None:
            continue

        bench = remaining_benches.pop(match_index)
        start_id = int(start["player_id"])
        bench_id = int(bench["player_id"])
        start_live = roster_by_id.get(start_id) or {}
        bench_live = roster_by_id.get(bench_id) or {}
        start_week = start_live.get("current_week") or {}
        bench_week = bench_live.get("current_week") or {}
        kickoff = (
            start_week.get("date")
            or bench_week.get("date")
            or "9999-12-31 23:59:59"
        )
        projected_gain = round(
            weekly_projection(start_live) - weekly_projection(bench_live),
            4,
        )
        commands.append({
            "schema": "waterboys.command.v1",
            "command_id": f"placement-lineup-{stamp}-pair-{index + 1}",
            "action": "lineup_move",
            "dry_run": False,
            "moves": [
                {
                    "player_id": bench_id,
                    "from_slot": str(bench["from_slot"]),
                    "to_slot": "BE",
                },
                {
                    "player_id": start_id,
                    "from_slot": str(start["from_slot"]),
                    "to_slot": to_slot,
                },
            ],
            "preconditions": {
                "reason": "automatic weekly placement-engine atomic lineup repair",
                "projected_lineup_leakage": optimizer.get("projected_lineup_leakage"),
                "projected_pair_gain": projected_gain,
                "kickoff": kickoff,
                "pair": {
                    "bench_player_id": bench_id,
                    "start_player_id": start_id,
                    "slot": to_slot,
                },
            },
        })

    commands.sort(
        key=lambda command: (
            str((command.get("preconditions") or {}).get("kickoff") or "9999-12-31 23:59:59"),
            -num((command.get("preconditions") or {}).get("projected_pair_gain")),
            str(command.get("command_id") or ""),
        )
    )
    return commands


def command_for_lineup_repair(snapshot: dict) -> dict | None:
    placement = snapshot.get("placement_engine") or {}
    optimizer = placement.get("lineup_optimizer") or {}
    changes = optimizer.get("recommended_changes") or {}
    moves = changes.get("moves") or []
    if not moves or changes.get("auto_executable") is not True:
        return None
    stamp = str(snapshot.get("collected_at") or "unknown").replace(":", "").replace("-", "").replace(".", "")
    return {
        "schema": "waterboys.command.v1",
        "command_id": f"placement-lineup-{stamp}",
        "action": "lineup_move",
        "dry_run": False,
        "moves": [
            {
                "player_id": int(move["player_id"]),
                "from_slot": str(move["from_slot"]),
                "to_slot": str(move["to_slot"]),
            }
            for move in moves
        ],
        "preconditions": {
            "reason": "automatic weekly placement-engine lineup repair",
            "projected_lineup_leakage": optimizer.get("projected_lineup_leakage"),
        },
    }


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


def _apply_claims_to_roster(
    roster: list[dict],
    claims: list[dict],
    player_by_id: dict,
) -> tuple[list[dict], list[dict], int]:
    result = list(roster)
    applied = []
    total_bid = 0
    for claim in claims:
        player_id = claim.get("player_id")
        candidate = player_by_id.get(player_id)
        if not candidate:
            continue
        drop_id = claim.get("dropped_player_id")
        if isinstance(drop_id, int):
            result = [player for player in result if player.get("player_id") != drop_id]
        if not any(player.get("player_id") == player_id for player in result):
            result.append(candidate)
        bid = int(claim.get("bid") or 0)
        total_bid += bid
        applied.append({
            "player_id": player_id,
            "player": claim.get("player") or candidate.get("name"),
            "bid": bid,
            "drop_player_id": drop_id,
            "drop_player": claim.get("dropped_player"),
        })
    return result, applied, total_bid


def _portfolio_projection(
    label: str,
    roster_after: list[dict],
    applied: list[dict],
    total_bid: int,
    waterboys: dict,
    survival: dict,
    roster_cfg: dict,
    base_weekly_risk: dict,
    current_points: float,
) -> dict:
    raw = optimize_weekly(roster_after, roster_cfg, risk_adjusted=False)
    risk = optimize_weekly(roster_after, roster_cfg, risk_adjusted=True)
    durable = optimize_durable(roster_after, roster_cfg)
    risk_delta = round(
        num(risk.get("risk_adjusted_projected_points"))
        - num(base_weekly_risk.get("risk_adjusted_projected_points")),
        4,
    )
    projected_points = round(current_points + risk_delta, 4)
    rank = projected_rank(projected_points, survival, waterboys.get("team_id"))
    current_rank = waterboys.get("current_week_projection_rank")
    rank_gain = (
        int(current_rank) - int(rank)
        if isinstance(current_rank, int) and isinstance(rank, int)
        else 0
    )
    return {
        "label": label,
        "claims": applied,
        "total_bid_if_all_clear": total_bid,
        "raw_optimized_weekly_points": raw.get("projected_points"),
        "risk_adjusted_optimized_weekly_points": risk.get("risk_adjusted_projected_points"),
        "risk_adjusted_weekly_gain": risk_delta,
        "estimated_projected_points": projected_points,
        "estimated_projection_rank": rank,
        "estimated_rank_gain": rank_gain,
        "durable_optimized_lineup_projected_ppg": durable.get("projected_ppg"),
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

    pending_claim_rows = [
        row for row in (waiver_offers or [])
        if row.get("team_id") == waterboys.get("team_id")
        and "PENDING" in str(row.get("result") or "").upper()
    ]
    pending_roster, pending_applied, pending_total_bid = _apply_claims_to_roster(
        roster, pending_claim_rows, player_by_id
    )
    pending_portfolio = _portfolio_projection(
        "all_current_pending_claims",
        pending_roster,
        pending_applied,
        pending_total_bid,
        waterboys,
        survival,
        roster_cfg,
        base_weekly_risk,
        current_points,
    )

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

    pending_ids = {row.get("player_id") for row in pending_claim_rows}
    next_launch_row = next(
        (
            row for row in durable_board
            if row.get("acquisition_path") == "waiver"
            and row.get("move_class") == "launch"
            and row.get("player_id") not in pending_ids
        ),
        None,
    )
    pending_plus_launch = None
    if next_launch_row:
        launch_player = player_by_id.get(next_launch_row.get("player_id"))
        if launch_player:
            overlay_roster = list(pending_roster)
            suggested_drop = next_launch_row.get("suggested_drop") or {}
            drop_id = suggested_drop.get("player_id")
            if isinstance(drop_id, int):
                overlay_roster = [
                    player for player in overlay_roster
                    if player.get("player_id") != drop_id
                ]
            if not any(
                player.get("player_id") == launch_player.get("player_id")
                for player in overlay_roster
            ):
                overlay_roster.append(launch_player)
            launch_bid = int(
                (next_launch_row.get("bid_guidance") or {}).get("recommended") or 0
            )
            overlay_claims = list(pending_applied) + [{
                "player_id": launch_player.get("player_id"),
                "player": launch_player.get("name"),
                "bid": launch_bid,
                "drop_player_id": drop_id,
                "drop_player": suggested_drop.get("name"),
                "status": "not_submitted_overlay",
            }]
            pending_plus_launch = _portfolio_projection(
                "pending_plus_best_unsubmitted_launch",
                overlay_roster,
                overlay_claims,
                pending_total_bid + launch_bid,
                waterboys,
                survival,
                roster_cfg,
                base_weekly_risk,
                current_points,
            )
            pending_plus_launch["overlay_target"] = {
                "player_id": next_launch_row.get("player_id"),
                "name": next_launch_row.get("name"),
                "recommended_bid": launch_bid,
                "injury_status": next_launch_row.get("injury_status"),
                "durable_risk_adjusted_marginal_ppg": next_launch_row.get(
                    "durable_risk_adjusted_marginal_ppg"
                ),
            }

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
            "starter_holes": base_weekly.get("starter_holes") or [],
            "optimized_lineup": base_weekly.get("players"),
        },
        "elimination_race": race,
        "future_elimination_targets": future_release_rows[:50],
        "best_acquisitions": board[:50],
        "weekly_rank_up_targets": weekly_board[:30],
        "durable_rank_up_targets": durable_board[:30],
        "portfolio_scenarios": {
            "pending_claims": pending_portfolio,
            "pending_plus_best_launch": pending_plus_launch,
        },
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
