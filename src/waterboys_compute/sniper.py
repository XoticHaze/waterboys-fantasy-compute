from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalize import utc_now


BLOCKED_INJURY = {"OUT", "INJURY_RESERVE", "DOUBTFUL"}
STARTER_SLOTS = {"QB", "RB", "WR", "TE", "RB/WR/TE", "FLEX", "D/ST", "K"}


def num(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _tier_for(row: dict, policy: dict) -> dict | None:
    risk = num(((row.get("value") or {}).get("risk_adjusted_marginal_ppg")))
    remaining = num(((row.get("value") or {}).get("expected_added_points_remaining")))
    eligible = []
    for tier in policy.get("tiers") or []:
        if (
            risk >= num(tier.get("min_risk_adjusted_marginal_ppg"))
            and remaining >= num(tier.get("min_expected_added_points_remaining"))
        ):
            eligible.append(tier)
    if not eligible:
        return None
    return max(eligible, key=lambda tier: int(tier.get("max_bid") or 0))


def _prior_observation(row: dict, previous_report: dict | None) -> dict | None:
    if not previous_report:
        return None
    pid = str(row.get("player_id"))
    return (previous_report.get("observations") or {}).get(pid)


def _confidence_signals(row: dict) -> dict:
    inputs = row.get("inputs") or {}
    projection = num(inputs.get("projected_avg_points"))
    current_week_projection = num(inputs.get("current_week_projected_points"))
    current_week_points = inputs.get("current_week_points")
    current_week_playable = (
        current_week_projection > 0
        or isinstance(current_week_points, (int, float))
    )
    recent = inputs.get("recent_form") or {}
    recent_median = num(recent.get("median"))
    season_avg = num(inputs.get("avg_points"))
    percent_started = num(inputs.get("percent_started"))

    return {
        "recent_median_support": (
            recent_median >= projection * 0.55 if projection > 0 and int(recent.get("games_count") or 0) >= 2 else False
        ),
        "season_average_support": season_avg >= projection * 0.55 if projection > 0 else False,
        "started_share_support": percent_started >= 35.0,
    }


def _placement_row(snapshot: dict, player_id: int | None) -> dict | None:
    if not isinstance(player_id, int):
        return None
    placement = snapshot.get("placement_engine") or {}
    boards = [
        placement.get("best_acquisitions") or [],
        placement.get("weekly_rank_up_targets") or [],
        placement.get("durable_rank_up_targets") or [],
    ]
    for board in boards:
        for row in board:
            if (
                row.get("player_id") == player_id
                and row.get("acquisition_path") == "waiver"
            ):
                return row
    return None


def _hole_accepts_position(hole: dict, position: str) -> bool:
    slot = str(hole.get("slot") or "")
    hole_position = str(hole.get("position") or "")
    if slot in {"RB/WR/TE", "FLEX"}:
        return position in {"RB", "WR", "TE"}
    return position == hole_position or position == slot


def _emergency_repair_context(
    row: dict,
    snapshot: dict,
    policy: dict,
) -> dict | None:
    cfg = policy.get("emergency_lineup_repair") or {}
    if cfg.get("enabled") is not True:
        return None

    inputs = row.get("inputs") or {}
    availability = str(inputs.get("availability_status") or "").upper()
    injury = str(inputs.get("injury_status") or "").upper()
    blocked = set(
        (policy.get("trap_guards") or {}).get("injury", {}).get("block_statuses")
        or BLOCKED_INJURY
    )
    if availability != "FREEAGENT" or injury in blocked:
        return None

    holes = list(
        ((snapshot.get("placement_engine") or {}).get("lineup_optimizer") or {}).get(
            "starter_holes"
        )
        or []
    )
    candidate_position = str(row.get("position") or "")
    matching = [
        hole for hole in holes
        if hole.get("game_locked") is not True
        and _hole_accepts_position(hole, candidate_position)
    ]
    if not matching:
        return None

    placement_row = _placement_row(snapshot, row.get("player_id"))
    if not placement_row:
        return None
    weekly_gain = num(placement_row.get("risk_adjusted_current_week_marginal_points"))
    min_gain = num(cfg.get("min_risk_adjusted_weekly_gain") or 3.0)
    if weekly_gain < min_gain:
        return None

    return {
        "hole": matching[0],
        "weekly_gain": weekly_gain,
        "estimated_rank_gain": int(placement_row.get("estimated_rank_gain") or 0),
    }


def _emergency_safe_drop(
    row: dict,
    snapshot: dict,
    emergency: dict | None,
) -> dict | None:
    if not emergency:
        return row.get("suggested_drop")

    roster = list((snapshot.get("waterboys") or {}).get("roster") or [])
    by_id = {player.get("player_id"): player for player in roster}
    candidate_pos = str(row.get("position") or "")
    hole = emergency.get("hole") or {}

    def locked(player: dict) -> bool:
        return isinstance((player.get("current_week") or {}).get("points"), (int, float))

    def descriptor(player: dict) -> dict:
        return {
            "player_id": player.get("player_id"),
            "name": player.get("name"),
            "position": player.get("position"),
            "projected_avg_points": player.get("projected_avg_points"),
        }

    hole_id = hole.get("player_id")
    hole_player = by_id.get(hole_id) if isinstance(hole_id, int) else None
    if (
        candidate_pos in {"K", "D/ST"}
        and hole_player
        and str(hole_player.get("lineup_slot") or "").upper() != "IR"
        and not locked(hole_player)
    ):
        return descriptor(hole_player)

    original = row.get("suggested_drop") or {}
    original_live = by_id.get(original.get("player_id")) or {}
    if (
        original_live
        and str(original_live.get("lineup_slot") or "").upper() == "BE"
        and not locked(original_live)
    ):
        return descriptor(original_live)

    limits = ((((snapshot.get("league") or {}).get("roster") or {}).get("position_limits")) or {})
    limit_key = "DST" if candidate_pos == "D/ST" else candidate_pos
    hard_limit = limits.get(limit_key)
    position_count = sum(
        1 for player in roster
        if str(player.get("position") or "") == candidate_pos
    )
    force_same_position = (
        isinstance(hard_limit, int) and position_count >= hard_limit
    )

    choices = []
    for player in roster:
        slot = str(player.get("lineup_slot") or "").upper()
        if slot != "BE" or locked(player):
            continue
        if force_same_position and str(player.get("position") or "") != candidate_pos:
            continue
        current_week = player.get("current_week") or {}
        current_projection = num(current_week.get("projected_points"))
        has_game = bool(current_week.get("opponent") or current_week.get("date"))
        unavailable_this_week = current_projection <= 0 and not has_game
        choices.append((
            0 if unavailable_this_week else 1,
            num(player.get("projected_avg_points")),
            player,
        ))

    if not choices:
        return None
    choices.sort(key=lambda item: (item[0], item[1]))
    return descriptor(choices[0][2])


def _growth_discipline_reason(
    snapshot: dict,
    policy: dict,
    player_id: int | None,
    bid: int,
) -> str | None:
    cfg = policy.get("growth_discipline") or {}
    if cfg.get("enabled") is not True:
        return None
    cheap_max = int(cfg.get("cheap_value_max_bid") or 25)
    if bid <= cheap_max:
        return None

    placement = snapshot.get("placement_engine") or {}
    pressure = str(placement.get("survival_pressure") or "").lower()
    placement_row = _placement_row(snapshot, player_id)
    if placement_row is None:
        if cfg.get("block_paid_move_without_placement_evidence") is True:
            return "paid_move_missing_placement_evidence"
        return None

    move_class = str(placement_row.get("move_class") or "").lower()
    if pressure == "red":
        allowed = {"material", "launch"}
    else:
        allowed = {"launch"}
    if move_class not in allowed:
        return "paid_middle_move_blocked"
    return None


def evaluate_candidate(row: dict, snapshot: dict, policy: dict, previous_report: dict | None = None) -> dict:
    inputs = row.get("inputs") or {}
    value = row.get("value") or {}
    availability = str(inputs.get("availability_status") or "").upper()
    injury = str(inputs.get("injury_status") or "").upper()
    risk = num(value.get("risk_adjusted_marginal_ppg"))
    remaining = num(value.get("expected_added_points_remaining"))
    projection = num(inputs.get("projected_avg_points"))
    recent = inputs.get("recent_form") or {}
    tier = _tier_for(row, policy)
    emergency = _emergency_repair_context(row, snapshot, policy)
    reasons = []

    if availability not in {"FREEAGENT", "WAIVERS"}:
        reasons.append("not_obtainable")
    if injury in set((policy.get("trap_guards") or {}).get("injury", {}).get("block_statuses") or BLOCKED_INJURY):
        reasons.append("blocked_injury_status")
    if tier is None:
        reasons.append("below_value_floor")

    drop = _emergency_safe_drop(row, snapshot, emergency)
    roster = list((snapshot.get("waterboys") or {}).get("roster") or [])
    roster_by_id = {p.get("player_id"): p for p in roster}
    roster_size = int((((snapshot.get("league") or {}).get("roster") or {}).get("size") or 14))
    active_roster_count = sum(
        1 for player in roster
        if str(player.get("lineup_slot") or "").upper() != "IR"
    )
    if drop:
        drop_live = roster_by_id.get(drop.get("player_id")) or {}
        drop_projection = num(drop.get("projected_avg_points"))
        if (
            active_roster_count >= roster_size
            and str(drop_live.get("lineup_slot") or "").upper() == "IR"
        ):
            reasons.append("suggested_drop_does_not_free_active_slot")
        if projection <= drop_projection:
            reasons.append("candidate_not_better_than_drop_asset")
        drop_week = drop_live.get("current_week") or {}
        current_points = drop_week.get("points")
        if isinstance(current_points, (int, float)):
            reasons.append("suggested_drop_may_be_game_locked")

        drop_slot = str(drop_live.get("lineup_slot") or "").upper()
        starter_slots = {"QB", "RB", "WR", "TE", "RB/WR/TE", "FLEX", "D/ST", "K"}
        if drop_slot in starter_slots and not isinstance(current_points, (int, float)):
            drop_week_projection = num(drop_week.get("projected_points"))
            candidate_pos = str(row.get("position") or "")
            slot_accepts_candidate = (
                drop_slot == candidate_pos
                or (
                    drop_slot in {"RB/WR/TE", "FLEX"}
                    and candidate_pos in {"RB", "WR", "TE"}
                )
                or (drop_slot == "D/ST" and candidate_pos == "D/ST")
            )
            if not current_week_playable:
                reasons.append("candidate_not_playable_this_week_for_starter_drop")
            elif not slot_accepts_candidate:
                reasons.append("starter_drop_without_direct_weekly_replacement")
            elif current_week_projection + 1e-9 < drop_week_projection:
                reasons.append("current_week_starter_downgrade")
    elif active_roster_count >= roster_size:
        reasons.append("full_roster_without_safe_drop")

    prior = _prior_observation(row, previous_report)
    max_decay = num(((policy.get("trap_guards") or {}).get("valuation") or {}).get("max_projection_drop_pct_since_first_seen") or 20)
    decay_pct = None
    if prior and num(prior.get("projected_avg_points")) > 0:
        prior_proj = num(prior.get("projected_avg_points"))
        decay_pct = round((prior_proj - projection) * 100.0 / prior_proj, 2)
        if decay_pct > max_decay:
            reasons.append("projection_value_decay")

    signals = _confidence_signals(row)
    signal_count = sum(1 for ok in signals.values() if ok)

    if emergency:
        tier = {"name": "emergency_lineup_repair", "max_bid": 0}
        reasons = [
            reason for reason in reasons
            if reason not in {"below_value_floor", "candidate_not_better_than_drop_asset"}
        ]

    stash_cfg = policy.get("free_stash") or {}
    if tier is None and availability == "FREEAGENT" and stash_cfg.get("enabled") is True:
        scarcity = num(value.get("value_over_best_free_replacement_ppg"))
        drop_projection = num((drop or {}).get("projected_avg_points"))
        projection_edge = projection - drop_projection
        if (
            drop
            and scarcity >= num(stash_cfg.get("min_replacement_scarcity_ppg") or 4.0)
            and projection_edge >= num(stash_cfg.get("min_projection_over_drop_ppg") or 2.0)
            and signal_count >= int(stash_cfg.get("min_independent_value_signals") or 2)
        ):
            tier = {"name": "free_stash", "max_bid": 0}
            reasons = [reason for reason in reasons if reason != "below_value_floor"]

    requested_max = int(tier.get("max_bid") or 0) if tier else 0
    priority = (policy.get("priority_caps") or {}).get(str(row.get("player_id"))) or {}
    priority_cap = int(priority.get("max_bid") or requested_max or 0)
    hard_cap = min(
        int(policy.get("global_max_bid") or 0),
        requested_max,
        priority_cap,
    ) if requested_max > 0 else 0

    bid_guidance = row.get("bid_guidance") or {}
    recommended = int(bid_guidance.get("recommended") or 0)
    reservation = int(bid_guidance.get("reservation_ceiling") or hard_cap or 0)
    hard_cap = min(hard_cap, reservation) if hard_cap > 0 and reservation > 0 else hard_cap

    guards = policy.get("trap_guards") or {}
    large_threshold = int((guards.get("valuation") or {}).get("large_bid_threshold") or 100)
    if availability == "WAIVERS" and hard_cap >= large_threshold:
        if injury == "QUESTIONABLE":
            reasons.append("questionable_blocks_large_bid")
        if int(recent.get("games_count") or 0) < int((guards.get("recent_form") or {}).get("min_games_for_large_bid") or 2):
            reasons.append("insufficient_recent_games_for_large_bid")
        max_share = recent.get("max_single_game_share")
        if isinstance(max_share, (int, float)) and max_share > num((guards.get("recent_form") or {}).get("max_single_game_share_of_recent_points") or 0.60):
            reasons.append("recent_scoring_outlier_concentration")
        if signal_count < 2:
            reasons.append("insufficient_independent_value_signals")

    budget = int((snapshot.get("waterboys") or {}).get("acquisition_budget_remaining") or 0)
    margin = num((snapshot.get("survival") or {}).get("waterboys_projected_margin_over_cutline"))
    bands = policy.get("survival_bands") or {}
    if margin >= num(bands.get("green_margin") or 25):
        reserve = int(policy.get("green_reserve_faab") or 0)
    elif margin >= num(bands.get("yellow_margin") or 12):
        reserve = int(policy.get("yellow_reserve_faab") or 0)
    else:
        reserve = int(policy.get("red_reserve_faab") or 0)
    budget_cap = max(0, budget - reserve)

    if availability == "FREEAGENT":
        action = "free_agent_add"
        bid = 0
    else:
        action = "waiver_claim"
        bid = min(max(1, recommended), hard_cap, budget_cap) if hard_cap > 0 and budget_cap > 0 else 0
        if bid <= 0:
            reasons.append("no_bid_capacity")
        market_conf = str((row.get("market_reference") or {}).get("confidence") or "")
        if bid >= large_threshold and market_conf == "low" and not priority:
            reasons.append("large_bid_low_market_confidence")
        discipline_reason = _growth_discipline_reason(
            snapshot,
            policy,
            row.get("player_id"),
            bid,
        )
        if discipline_reason:
            reasons.append(discipline_reason)

    return {
        "player_id": row.get("player_id"),
        "name": row.get("name"),
        "position": row.get("position"),
        "availability": availability,
        "injury_status": injury,
        "tier": tier.get("name") if tier else None,
        "risk_adjusted_marginal_ppg": risk,
        "expected_added_points_remaining": remaining,
        "projected_avg_points": projection,
        "current_week_projected_points": current_week_projection,
        "current_week_playable": current_week_playable,
        "recent_form": recent,
        "signals": signals,
        "signal_count": signal_count,
        "projection_decay_pct": decay_pct,
        "suggested_drop": drop,
        "action": action,
        "recommended_bid": recommended,
        "hard_cap": hard_cap,
        "selected_bid": bid,
        "placement_move_class": ((_placement_row(snapshot, row.get("player_id")) or {}).get("move_class")),
        "estimated_rank_gain": ((_placement_row(snapshot, row.get("player_id")) or {}).get("estimated_rank_gain")),
        "emergency_repair": emergency is not None,
        "emergency_hole": (emergency or {}).get("hole"),
        "emergency_weekly_gain": (emergency or {}).get("weekly_gain"),
        "eligible": not reasons,
        "reasons": reasons,
    }


def _pending_rows(snapshot: dict) -> list[dict]:
    team_id = (snapshot.get("waterboys") or {}).get("team_id")
    rows = []
    for row in snapshot.get("waiver_offers") or []:
        if row.get("team_id") != team_id:
            continue
        if "PENDING" not in str(row.get("result") or "").upper():
            continue
        rows.append(row)
    return rows


def plan_sniper(snapshot: dict, policy: dict, previous_report: dict | None = None) -> dict:
    rows = list(((snapshot.get("value_engine") or {}).get("waiver_targets") or []))
    evaluations = [evaluate_candidate(row, snapshot, policy, previous_report) for row in rows]

    pending = _pending_rows(snapshot)
    pending_ids = {row.get("player_id") for row in pending}
    cancel_actions = []
    by_id = {row.get("player_id"): row for row in evaluations}
    for pending_row in pending:
        candidate = by_id.get(pending_row.get("player_id"))
        if candidate is None or not candidate.get("eligible"):
            cancel_actions.append({
                "action": "waiver_cancel",
                "transaction_id": pending_row.get("offer_id"),
                "player_id": pending_row.get("player_id"),
                "player": pending_row.get("player"),
                "reason": "pending claim no longer passes current sniper gates",
            })
            continue
        current_bid = int(pending_row.get("bid") or 0)
        repriced = int(candidate.get("selected_bid") or 0)
        if repriced > 0 and current_bid > repriced:
            replacement = dict(candidate)
            replacement["selected_bid"] = repriced
            cancel_actions.append({
                "action": "waiver_cancel",
                "transaction_id": pending_row.get("offer_id"),
                "player_id": pending_row.get("player_id"),
                "player": pending_row.get("player"),
                "reason": f"current bid {current_bid} exceeds repriced bid {repriced}",
                "replacement_bid": repriced,
                "replacement_selection": replacement,
            })

    eligible = [
        row for row in evaluations
        if row.get("eligible") and row.get("player_id") not in pending_ids
    ]
    eligible.sort(
        key=lambda row: (
            1 if row.get("emergency_repair") else 0,
            num(row.get("emergency_weekly_gain")),
            num(row.get("risk_adjusted_marginal_ppg")),
            num(row.get("expected_added_points_remaining")),
            -int(row.get("selected_bid") or 0),
        ),
        reverse=True,
    )

    max_actions = int(policy.get("max_actions_per_run") or 1)
    selected = []
    free_agent_selected = False
    for row in eligible:
        if len(selected) >= max_actions:
            break
        if row.get("action") == "free_agent_add":
            if free_agent_selected:
                continue
            free_agent_selected = True
        selected.append(row)

    observations = {
        str(row.get("player_id")): {
            "name": row.get("name"),
            "projected_avg_points": row.get("projected_avg_points"),
            "risk_adjusted_marginal_ppg": row.get("risk_adjusted_marginal_ppg"),
            "injury_status": row.get("injury_status"),
            "recent_form": row.get("recent_form"),
            "selected_bid": row.get("selected_bid"),
            "eligible": row.get("eligible"),
            "reasons": row.get("reasons"),
        }
        for row in evaluations[:100]
    }

    return {
        "schema": "waterboys.sniper_report.v1",
        "created_at": utc_now(),
        "snapshot_collected_at": snapshot.get("collected_at"),
        "mode": str(policy.get("mode") or "shadow"),
        "enabled": policy.get("enabled") is True,
        "cancel_actions": cancel_actions,
        "selected": selected,
        "top_evaluations": evaluations[:50],
        "observations": observations,
    }


def command_for_selection(selection: dict, snapshot: dict) -> dict:
    stamp = str(snapshot.get("collected_at") or "unknown").replace(":", "").replace("-", "").replace(".", "")
    player_id = int(selection["player_id"])
    action = str(selection["action"])
    command = {
        "schema": "waterboys.command.v1",
        "command_id": f"sniper-{stamp}-{player_id}",
        "action": action,
        "dry_run": False,
        "player_id": player_id,
        "preconditions": {
            "player_name": selection.get("name"),
            "sniper_tier": selection.get("tier"),
            "risk_adjusted_marginal_ppg": selection.get("risk_adjusted_marginal_ppg"),
            "hard_cap": selection.get("hard_cap"),
        },
    }
    drop = selection.get("suggested_drop")
    if isinstance(drop, dict) and isinstance(drop.get("player_id"), int):
        command["drop_player_id"] = drop["player_id"]
    if action == "waiver_claim":
        command["faab_bid"] = int(selection.get("selected_bid") or 0)
    return command


def command_for_cancel(cancel: dict, snapshot: dict) -> dict:
    stamp = str(snapshot.get("collected_at") or "unknown").replace(":", "").replace("-", "").replace(".", "")
    transaction_id = str(cancel.get("transaction_id") or "")
    transaction_suffix = transaction_id.replace("-", "")[:10] or "unknown"
    return {
        "schema": "waterboys.command.v1",
        "command_id": f"sniper-cancel-{stamp}-{cancel.get('player_id')}-{transaction_suffix}",
        "action": "waiver_cancel",
        "dry_run": False,
        "transaction_id": str(cancel.get("transaction_id") or ""),
        "preconditions": {
            "player_name": cancel.get("player"),
            "reason": cancel.get("reason"),
        },
    }
