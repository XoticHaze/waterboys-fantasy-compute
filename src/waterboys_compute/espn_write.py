from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SLOT_IDS = {
    "QB": 0,
    "RB": 2,
    "WR": 4,
    "TE": 6,
    "D/ST": 16,
    "DST": 16,
    "K": 17,
    "BE": 20,
    "IR": 21,
    "RB/WR/TE": 23,
    "FLEX": 23,
}

READ_HOST = "https://lm-api-reads.fantasy.espn.com"
WRITE_HOST = "https://lm-api-writes.fantasy.espn.com"


def _league_parts(runtime: dict) -> tuple[int, int, int, str, str]:
    league = runtime.get("league") or {}
    league_id = int(league.get("league_id") or 0)
    season = int(league.get("season") or 0)
    team_id = int(league.get("team_id") or 0)
    swid = str(runtime.get("swid") or "")
    espn_s2 = str(runtime.get("espn_s2") or "")
    if league_id <= 0 or season <= 0 or team_id <= 0 or not swid or not espn_s2:
        raise RuntimeError("ESPN write runtime is incomplete")
    return league_id, season, team_id, swid, espn_s2


def _league_url(host: str, runtime: dict) -> str:
    league_id, season, _, _, _ = _league_parts(runtime)
    return (
        f"{host}/apis/v3/games/ffl/seasons/{season}/segments/0/"
        f"leagues/{league_id}"
    )


def _headers(runtime: dict) -> dict:
    _, _, _, swid, espn_s2 = _league_parts(runtime)
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "cookie": f"espn_s2={espn_s2}; SWID={swid}",
        "user-agent": "waterboys-fantasy-compute/0.1",
    }


def _json_request(runtime: dict, url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = Request(url, data=payload, method=method, headers=_headers(runtime))
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"ESPN write request failed: HTTP {exc.code}: {detail}") from exc


def pending_transactions(runtime: dict) -> list[dict]:
    query = urlencode({"view": "mPendingTransactions"})
    _, data = _json_request(runtime, _league_url(READ_HOST, runtime) + "?" + query)
    pending = data.get("pendingTransactions")
    return list(pending) if isinstance(pending, list) else []


def post_transaction(runtime: dict, body: dict) -> tuple[int, dict]:
    url = _league_url(WRITE_HOST, runtime) + "/transactions/"
    return _json_request(runtime, url, method="POST", body=body)


def _slot_id(value: object) -> int:
    if isinstance(value, int):
        return value
    key = str(value or "").upper()
    if key not in SLOT_IDS:
        raise RuntimeError(f"unsupported ESPN lineup slot: {value}")
    return SLOT_IDS[key]


def build_transaction(runtime: dict, command: dict, fresh: dict) -> dict:
    _, _, team_id, swid, _ = _league_parts(runtime)
    league = fresh.get("league") or {}
    scoring_period = int(league.get("nfl_week") or league.get("current_week") or 1)
    action = str(command.get("action") or "")

    base = {
        "isLeagueManager": False,
        "teamId": team_id,
        "memberId": swid,
        "scoringPeriodId": scoring_period,
        "executionType": "EXECUTE",
    }

    if action in {"waiver_claim", "free_agent_add"}:
        player_id = command.get("player_id")
        if not isinstance(player_id, int):
            raise RuntimeError(f"{action} requires integer player_id")
        items = [{"playerId": player_id, "type": "ADD", "toTeamId": team_id}]
        drop_player_id = command.get("drop_player_id")
        if drop_player_id is not None:
            if not isinstance(drop_player_id, int):
                raise RuntimeError(f"{action} drop_player_id must be an integer")
            items.append({"playerId": drop_player_id, "type": "DROP", "fromTeamId": team_id})
        base["type"] = "WAIVER" if action == "waiver_claim" else "FREEAGENT"
        base["items"] = items
        if action == "waiver_claim":
            bid = command.get("faab_bid")
            if not isinstance(bid, int) or bid < 0:
                raise RuntimeError("waiver_claim requires non-negative integer faab_bid")
            base["bidAmount"] = bid
        return base

    if action == "free_agent_drop":
        player_id = command.get("player_id")
        if not isinstance(player_id, int):
            raise RuntimeError("free_agent_drop requires integer player_id")
        base["type"] = "FREEAGENT"
        base["items"] = [
            {"playerId": player_id, "type": "DROP", "fromTeamId": team_id}
        ]
        return base

    if action == "waiver_cancel":
        transaction_id = str(command.get("transaction_id") or "")
        if not transaction_id:
            raise RuntimeError("waiver_cancel requires transaction_id")
        base["type"] = "WAIVER"
        base["executionType"] = "CANCEL"
        base["relatedTransactionId"] = transaction_id
        return base

    if action in {"lineup_move", "ir_move"}:
        moves = command.get("moves")
        if not isinstance(moves, list) or not moves:
            player_id = command.get("player_id")
            if not isinstance(player_id, int):
                raise RuntimeError(f"{action} requires player_id or moves")
            moves = [{
                "player_id": player_id,
                "from_slot": command.get("from_slot"),
                "to_slot": "IR" if action == "ir_move" else command.get("to_slot"),
            }]
        items = []
        for move in moves:
            if not isinstance(move, dict) or not isinstance(move.get("player_id"), int):
                raise RuntimeError("lineup moves require integer player_id")
            items.append({
                "playerId": move["player_id"],
                "type": "LINEUP",
                "fromLineupSlotId": _slot_id(move.get("from_slot")),
                "toLineupSlotId": _slot_id(move.get("to_slot")),
            })
        base["type"] = "ROSTER"
        base["items"] = items
        return base

    raise RuntimeError(f"unsupported live ESPN action: {action}")


def redacted_transaction(body: dict) -> dict:
    safe = json.loads(json.dumps(body))
    if "memberId" in safe:
        safe["memberId"] = "[REDACTED]"
    return safe


def validate_preflight(command: dict, fresh: dict) -> None:
    waterboys = fresh.get("waterboys") or {}
    roster = list(waterboys.get("roster") or [])
    roster_ids = {player.get("player_id") for player in roster}
    free_agents = list(fresh.get("free_agents") or [])
    free_ids = {player.get("player_id") for player in free_agents}
    action = str(command.get("action") or "")

    if action in {"waiver_claim", "free_agent_add"}:
        player_id = command.get("player_id")
        if player_id not in free_ids:
            raise RuntimeError("target player is not in the fresh available-player pool")
        drop_id = command.get("drop_player_id")
        if drop_id is not None and drop_id not in roster_ids:
            raise RuntimeError("drop player is not on the fresh WaterBoys roster")

    if action == "free_agent_drop":
        player_id = command.get("player_id")
        if player_id not in roster_ids:
            raise RuntimeError("drop player is not on the fresh WaterBoys roster")

    if action == "waiver_claim":
        bid = command.get("faab_bid")
        budget = int(waterboys.get("acquisition_budget_remaining") or 0)
        if not isinstance(bid, int) or bid < 0 or bid > budget:
            raise RuntimeError("FAAB bid exceeds the fresh WaterBoys budget")

    if action in {"lineup_move", "ir_move"}:
        moves = command.get("moves") if isinstance(command.get("moves"), list) else [command]
        for move in moves:
            if move.get("player_id") not in roster_ids:
                raise RuntimeError("lineup player is not on the fresh WaterBoys roster")


def verify_pending_claim(runtime: dict, command: dict) -> dict:
    _, _, team_id, _, _ = _league_parts(runtime)
    target_id = command.get("player_id")
    expected_bid = command.get("faab_bid")
    matches = []
    for transaction in pending_transactions(runtime):
        if int(transaction.get("teamId") or 0) != team_id:
            continue
        if str(transaction.get("type") or "").upper() != "WAIVER":
            continue
        adds = [
            item.get("playerId")
            for item in transaction.get("items") or []
            if str(item.get("type") or "").upper() == "ADD"
        ]
        if target_id not in adds:
            continue
        if expected_bid is not None and int(transaction.get("bidAmount") or 0) != int(expected_bid):
            continue
        matches.append(transaction)
    return {
        "verified": bool(matches),
        "transaction_id": str(matches[0].get("id")) if matches else None,
        "pending_match_count": len(matches),
    }


def verify_cancel(runtime: dict, transaction_id: str) -> dict:
    ids = {str(row.get("id")) for row in pending_transactions(runtime)}
    return {"verified": transaction_id not in ids, "transaction_id": transaction_id}
