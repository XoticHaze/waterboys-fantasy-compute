from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalize import utc_now


BLOCKED_INJURY = {"OUT", "INJURY_RESERVE", "DOUBTFUL"}


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
    reasons = []

    if availability not in {"FREEAGENT", "WAIVERS"}:
        reasons.append("not_obtainable")
    if injury in set((policy.get("trap_guards") or {}).get("injury", {}).get("block_statuses") or BLOCKED_INJURY):
        reasons.append("blocked_injury_status")
    if tier is None:
        reasons.append("below_value_floor")

    drop = row.get("suggested_drop")
    roster = list((snapshot.get("waterboys") or {}).get("roster") or [])
    roster_by_id = {p.get("player_id"): p for p in roster}
    if drop:
        drop_live = roster_by_id.get(drop.get("player_id")) or {}
        drop_projection = num(drop.get("projected_avg_points"))
        if projection <= drop_projection:
            reasons.append("candidate_not_better_than_drop_asset")
        current_points = ((drop_live.get("current_week") or {}).get("points"))
        if isinstance(current_points, (int, float)):
            reasons.append("suggested_drop_may_be_game_locked")
    elif len(roster) >= int((((snapshot.get("league") or {}).get("roster") or {}).get("size") or 14)):
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
        "recent_form": recent,
        "signals": signals,
        "signal_count": signal_count,
        "projection_decay_pct": decay_pct,
        "suggested_drop": drop,
        "action": action,
        "recommended_bid": recommended,
        "hard_cap": hard_cap,
        "selected_bid": bid,
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
        if repriced > 0 and current_bid > repriced and current_bid - repriced >= max(5, int(current_bid * 0.20)):
            cancel_actions.append({
                "action": "waiver_cancel",
                "transaction_id": pending_row.get("offer_id"),
                "player_id": pending_row.get("player_id"),
                "player": pending_row.get("player"),
                "reason": f"current bid {current_bid} materially exceeds repriced bid {repriced}",
                "replacement_bid": repriced,
            })

    eligible = [
        row for row in evaluations
        if row.get("eligible") and row.get("player_id") not in pending_ids
    ]
    eligible.sort(
        key=lambda row: (
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
    return {
        "schema": "waterboys.command.v1",
        "command_id": f"sniper-cancel-{stamp}-{cancel.get('player_id')}",
        "action": "waiver_cancel",
        "dry_run": False,
        "transaction_id": str(cancel.get("transaction_id") or ""),
        "preconditions": {
            "player_name": cancel.get("player"),
            "reason": cancel.get("reason"),
        },
    }
