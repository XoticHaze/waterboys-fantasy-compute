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


def risk_adjusted_optimize(players: list[dict], roster_cfg: dict) -> dict:
    adjusted = []
    for player in players:
        row = dict(player)
        row["projected_avg_points"] = round(
            num(player.get("projected_avg_points")) * availability(player),
            4,
        )
        adjusted.append(row)
    return optimize(adjusted, roster_cfg)


def _swap_roster(
    roster: list[dict],
    outgoing_id: int | None,
    incoming: dict,
) -> list[dict]:
    result = [
        player for player in roster
        if player.get("player_id") != outgoing_id
    ]
    result.append(incoming)
    return result


def build_trade_exchange_board(
    waterboys: dict,
    teams: list[dict],
    free_agents: list[dict],
    roster_cfg: dict,
    weeks: int,
) -> tuple[list[dict], list[dict]]:
    our_roster = list(waterboys.get("roster") or [])
    our_id = waterboys.get("team_id")
    eligible_positions = {"QB", "RB", "WR", "TE"}
    our_assets = [
        player for player in our_roster
        if player.get("position") in eligible_positions
        and str(player.get("lineup_slot") or "").upper() != "IR"
    ]
    our_base = risk_adjusted_optimize(our_roster, roster_cfg)
    exchanges = []

    for team in teams:
        if team.get("team_id") == our_id or int(team.get("roster_count") or 0) <= 0:
            continue
        rival_roster = list(team.get("roster") or [])
        rival_base = risk_adjusted_optimize(rival_roster, roster_cfg)

        for incoming in rival_roster:
            if incoming.get("position") not in eligible_positions:
                continue
            if str(incoming.get("lineup_slot") or "").upper() == "IR":
                continue

            for outgoing in our_assets:
                if outgoing.get("player_id") == incoming.get("player_id"):
                    continue

                our_after = risk_adjusted_optimize(
                    _swap_roster(
                        our_roster,
                        outgoing.get("player_id"),
                        incoming,
                    ),
                    roster_cfg,
                )
                rival_after = risk_adjusted_optimize(
                    _swap_roster(
                        rival_roster,
                        incoming.get("player_id"),
                        outgoing,
                    ),
                    roster_cfg,
                )
                our_delta = round(
                    num(our_after.get("projected_ppg"))
                    - num(our_base.get("projected_ppg")),
                    4,
                )
                rival_delta = round(
                    num(rival_after.get("projected_ppg"))
                    - num(rival_base.get("projected_ppg")),
                    4,
                )
                if our_delta <= 0:
                    continue

                incoming_scarcity, incoming_replacement = replacement(
                    incoming, free_agents
                )
                outgoing_scarcity, outgoing_replacement = replacement(
                    outgoing, free_agents
                )
                mutual = rival_delta >= 0
                acceptance = (
                    "mutual_gain"
                    if mutual and rival_delta > 0
                    else "rival_flat"
                    if mutual
                    else "rival_concession_needed"
                )
                exchanges.append({
                    "trade_type": "one_for_one",
                    "source_team_id": team.get("team_id"),
                    "source_team": team.get("name"),
                    "incoming": {
                        "player_id": incoming.get("player_id"),
                        "name": incoming.get("name"),
                        "position": incoming.get("position"),
                        "injury_status": incoming.get("injury_status"),
                        "projected_avg_points": incoming.get("projected_avg_points"),
                        "availability_factor": availability(incoming),
                        "scarcity_over_best_free_ppg": incoming_scarcity,
                        "best_free_replacement": incoming_replacement,
                    },
                    "outgoing": {
                        "player_id": outgoing.get("player_id"),
                        "name": outgoing.get("name"),
                        "position": outgoing.get("position"),
                        "injury_status": outgoing.get("injury_status"),
                        "projected_avg_points": outgoing.get("projected_avg_points"),
                        "availability_factor": availability(outgoing),
                        "scarcity_over_best_free_ppg": outgoing_scarcity,
                        "best_free_replacement": outgoing_replacement,
                    },
                    "waterboys_risk_adjusted_ppg_gain": our_delta,
                    "waterboys_expected_added_points_remaining": round(
                        our_delta * weeks, 2
                    ),
                    "counterparty_risk_adjusted_ppg_gain": rival_delta,
                    "mutually_beneficial": mutual,
                    "acceptance_signal": acceptance,
                    "exchange_score": round(
                        our_delta + 0.5 * max(0.0, rival_delta),
                        4,
                    ),
                })

    exchanges.sort(
        key=lambda row: (
            row.get("mutually_beneficial") is True,
            num(row.get("exchange_score")),
            num(row.get("waterboys_risk_adjusted_ppg_gain")),
        ),
        reverse=True,
    )

    assets = []
    for player in our_assets:
        without = [
            row for row in our_roster
            if row.get("player_id") != player.get("player_id")
        ]
        removal_loss = round(
            num(our_base.get("projected_ppg"))
            - num(risk_adjusted_optimize(without, roster_cfg).get("projected_ppg")),
            4,
        )
        scarcity, replacement_name = replacement(player, free_agents)
        options = [
            row for row in exchanges
            if (row.get("outgoing") or {}).get("player_id") == player.get("player_id")
        ]
        mutual_options = [
            row for row in options
            if row.get("mutually_beneficial") is True
        ]
        best = options[0] if options else None
        trade_before_drop = (
            scarcity >= 2.0
            and removal_loss <= 1.0
            and bool(mutual_options)
        )
        assets.append({
            "player_id": player.get("player_id"),
            "name": player.get("name"),
            "position": player.get("position"),
            "injury_status": player.get("injury_status"),
            "lineup_slot": player.get("lineup_slot"),
            "risk_adjusted_lineup_loss_if_removed_ppg": removal_loss,
            "scarcity_over_best_free_ppg": scarcity,
            "best_free_replacement": replacement_name,
            "mutually_beneficial_trade_count": len(mutual_options),
            "positive_waterboys_trade_count": len(options),
            "trade_before_drop": trade_before_drop,
            "best_trade_return": (
                {
                    "source_team_id": best.get("source_team_id"),
                    "source_team": best.get("source_team"),
                    "incoming": best.get("incoming"),
                    "waterboys_risk_adjusted_ppg_gain": best.get(
                        "waterboys_risk_adjusted_ppg_gain"
                    ),
                    "counterparty_risk_adjusted_ppg_gain": best.get(
                        "counterparty_risk_adjusted_ppg_gain"
                    ),
                    "mutually_beneficial": best.get("mutually_beneficial"),
                }
                if best else None
            ),
        })

    assets.sort(
        key=lambda row: (
            row.get("trade_before_drop") is True,
            int(row.get("mutually_beneficial_trade_count") or 0),
            num(row.get("scarcity_over_best_free_ppg")),
            -num(row.get("risk_adjusted_lineup_loss_if_removed_ppg")),
        ),
        reverse=True,
    )
    return exchanges[:100], assets


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
        if (
            candidate_pos in {"K", "D/ST"} and counts.get(candidate_pos, 0) > 0
        ) or (
            isinstance(hard_limit, int) and counts.get(candidate_pos, 0) >= hard_limit
        )
        else None
    )

    choices = []
    for player in roster:
        if str(player.get("lineup_slot") or "").upper() == "IR":
            continue
        if isinstance((player.get("current_week") or {}).get("points"), (int, float)):
            continue
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


def percentile(values: list[int], fraction: float) -> int | None:
    clean = sorted(int(value) for value in values if isinstance(value, (int, float)) and value >= 0)
    if not clean:
        return None
    index = int(round((len(clean) - 1) * max(0.0, min(1.0, fraction))))
    return clean[index]


def market_reference(candidate: dict, market: dict | None, waiver_offers: list[dict] | None) -> dict:
    rows = []
    seen = set()
    for row in (market or {}).get("successful_waiver_bids") or []:
        bid = row.get("bid")
        if not isinstance(bid, (int, float)) or bid <= 0:
            continue
        key = (row.get("player_id"), row.get("team_id"), int(bid))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "player_id": row.get("player_id"),
            "player": row.get("player"),
            "position": row.get("position"),
            "projected_avg_points": row.get("projected_avg_points"),
            "bid": int(bid),
            "kind": "winning_bid",
        })

    for row in waiver_offers or []:
        bid = row.get("bid")
        result = str(row.get("result") or "").upper()
        if (
            not isinstance(bid, (int, float))
            or bid <= 0
            or any(marker in result for marker in ("PENDING", "CANCELED", "CANCELLED"))
        ):
            continue
        key = (row.get("player_id"), row.get("team_id"), int(bid))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "player_id": row.get("player_id"),
            "player": row.get("player"),
            "position": row.get("position"),
            "projected_avg_points": row.get("projected_avg_points"),
            "bid": int(bid),
            "kind": "processed_offer",
        })

    candidate_pos = candidate.get("position")
    candidate_proj = num(candidate.get("projected_avg_points"))
    same_position = [row for row in rows if row.get("position") == candidate_pos]
    comparable = [
        row for row in same_position
        if isinstance(row.get("projected_avg_points"), (int, float))
        and abs(float(row["projected_avg_points"]) - candidate_proj) <= max(4.0, candidate_proj * 0.30)
    ]
    sample = comparable or same_position or rows
    bids = [row["bid"] for row in sample]
    confidence = "high" if len(sample) >= 6 else "medium" if len(sample) >= 3 else "low"

    return {
        "sample_basis": (
            "same_position_similar_projection" if comparable
            else "same_position" if same_position
            else "all_observed_winners_and_processed_offers"
        ),
        "sample_size": len(sample),
        "confidence": confidence,
        "median": percentile(bids, 0.50),
        "p75": percentile(bids, 0.75),
        "p90": percentile(bids, 0.90),
        "max": max(bids) if bids else None,
        "recent_comparables": sorted(sample, key=lambda row: row["bid"], reverse=True)[:5],
    }


def calibrated_bid_guidance(value_reference: dict, market_ref: dict, risk_delta: float, budget: int) -> dict:
    if not value_reference.get("applicable"):
        return {"applicable": False, "reason": value_reference.get("reason")}

    ceiling = int(value_reference.get("high") or value_reference.get("midpoint") or 0)
    observed = int(market_ref.get("sample_size") or 0)
    if observed <= 0:
        return {
            "applicable": True,
            "confidence": "unpriced",
            "recommended": int(value_reference.get("midpoint") or 0),
            "reservation_ceiling": ceiling,
            "reason": "No comparable league clearing-price sample yet; use value reference cautiously.",
        }

    median = int(market_ref.get("median") or 0)
    p75 = int(market_ref.get("p75") or median)
    p90 = int(market_ref.get("p90") or p75)
    anchor = p90 if risk_delta >= 10 else p75 if risk_delta >= 3 else median
    protection = max(1, int(round(max(1, budget) * 0.005)))
    recommended = min(ceiling, max(1, anchor + protection))

    return {
        "applicable": True,
        "confidence": market_ref.get("confidence"),
        "recommended": recommended,
        "reservation_ceiling": ceiling,
        "market_anchor": anchor,
        "protection_margin": protection,
        "reason": "Recommended bid is market-clearing estimate plus protection, capped by player-value reservation ceiling.",
    }


def score_candidate(candidate: dict, source: str, waterboys: dict, free_agents: list[dict],
                    roster_cfg: dict, weeks: int, budget: int, source_team: dict | None = None,
                    market: dict | None = None, waiver_offers: list[dict] | None = None) -> dict:
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
            "acquisition_type": candidate.get("acquisition_type"),
            "availability_status": candidate.get("availability_status"),
            "availability_factor": health,
            "percent_owned": candidate.get("percent_owned"),
            "percent_started": candidate.get("percent_started"),
            "positional_rank": candidate.get("positional_rank"),
            "current_week_projected_points": (
                (candidate.get("current_week") or {}).get("projected_points")
            ),
            "current_week_points": (
                (candidate.get("current_week") or {}).get("points")
            ),
            "current_week_opponent": (
                (candidate.get("current_week") or {}).get("opponent")
            ),
            "current_week_date": (
                (candidate.get("current_week") or {}).get("date")
            ),
            "recent_form": candidate.get("recent_form") or {},
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
    market_ref = market_reference(candidate, market, waiver_offers)
    result["market_reference"] = market_ref
    result["bid_guidance"] = calibrated_bid_guidance(
        result["faab_reference"], market_ref, risk, budget
    )
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
                       survival: dict, league_cfg: dict, settings: dict,
                       market: dict | None = None, waiver_offers: list[dict] | None = None) -> dict:
    roster_cfg = league_cfg.get("roster") or {}
    current_week = int(league_cfg.get("current_week") or 0)
    weeks = max(0, int(settings.get("regular_season_count") or current_week) - current_week)
    budget = int(waterboys.get("acquisition_budget_remaining") or
                 (league_cfg.get("waivers") or {}).get("faab_start") or 0)

    waivers = [
        score_candidate(
            p, "free_agent", waterboys, free_agents, roster_cfg, weeks, budget,
            market=market, waiver_offers=waiver_offers
        )
        for p in free_agents if p.get("position") in {"QB", "RB", "WR", "TE", "D/ST", "K"}
    ]

    risk_id = (survival.get("elimination_watch") or {}).get("team_id")
    risk_team = next((t for t in teams if t.get("team_id") == risk_id), None)
    releases = []
    if risk_team:
        releases = [
            score_candidate(
                p, "elimination_watch", waterboys, free_agents, roster_cfg,
                weeks, budget, risk_team, market=market, waiver_offers=waiver_offers
            )
            for p in risk_team.get("roster") or []
            if p.get("position") in {"QB", "RB", "WR", "TE", "D/ST", "K"}
        ]

    projected_risk_id = (survival.get("projected_elimination_watch") or {}).get("team_id")
    projected_risk_team = next((t for t in teams if t.get("team_id") == projected_risk_id), None)
    projected_releases = []
    if projected_risk_team:
        projected_releases = [
            score_candidate(
                p, "projected_elimination_watch", waterboys, free_agents, roster_cfg,
                weeks, budget, projected_risk_team, market=market, waiver_offers=waiver_offers
            )
            for p in projected_risk_team.get("roster") or []
            if p.get("position") in {"QB", "RB", "WR", "TE", "D/ST", "K"}
        ]

    trades = []
    for team in teams:
        if team.get("team_id") in {waterboys.get("team_id"), risk_id} or int(team.get("roster_count") or 0) <= 0:
            continue
        trades.extend(
            score_candidate(
                p, "trade", waterboys, free_agents, roster_cfg, weeks, budget, team,
                market=market, waiver_offers=waiver_offers
            )
            for p in team.get("roster") or []
            if p.get("position") in {"QB", "RB", "WR", "TE"}
        )

    key = lambda row: (
        num(row["value"]["risk_adjusted_marginal_ppg"]),
        num(row["value"]["value_over_best_free_replacement_ppg"]),
    )
    waivers.sort(key=key, reverse=True)
    releases.sort(key=key, reverse=True)
    projected_releases.sort(key=key, reverse=True)
    trades.sort(key=key, reverse=True)
    base = optimize(list(waterboys.get("roster") or []), roster_cfg)

    return {
        "schema": "waterboys.value_engine.v1", "status": "advisory",
        "methodology": {
            "basis": "ESPN projected average points under this league scoring.",
            "marginal_lineup_ppg": "Optimized WaterBoys lineup with candidate minus current optimized lineup.",
            "replacement_value": "Candidate projection minus best free alternative at the same position.",
            "health_factors": HEALTH,
            "faab_reference": "Player-value reservation range; not a clearing-price estimate.",
            "market_reference": "Observed league winning bids and processed waiver offers, preferring same-position/projection comparables.",
            "bid_guidance": "Market anchor plus a small protection margin, capped by the player-value reservation ceiling.",
            "trade_targets": "Gross acquisition value; outgoing-player cost is not included.",
        },
        "waterboys_baseline": {
            "optimized_lineup_projected_ppg": base["projected_ppg"],
            "optimized_lineup": base["players"], "faab_remaining": budget,
            "weeks_remaining": weeks,
        },
        "waiver_targets": waivers[:75],
        "elimination_watch_targets": releases[:25],
        "projected_elimination_watch_targets": projected_releases[:25],
        "trade_targets": trades[:75],
    }
