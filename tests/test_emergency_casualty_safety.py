from waterboys_compute.sniper import _emergency_safe_drop


def player(pid, name, pos, slot, projected_avg, weekly=0, points=None, opponent=None, date=None):
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "lineup_slot": slot,
        "injury_status": "ACTIVE",
        "projected_avg_points": projected_avg,
        "current_week": {
            "projected_points": weekly,
            "points": points,
            "opponent": opponent,
            "date": date,
        },
    }


def snapshot(roster):
    return {
        "waterboys": {"roster": roster},
        "league": {
            "roster": {
                "position_limits": {
                    "QB": 2,
                    "RB": 5,
                    "WR": 5,
                    "TE": 3,
                    "DST": 3,
                    "K": 2,
                }
            }
        },
    }


def test_emergency_kicker_repair_drops_bye_kicker_not_unrelated_starter():
    reichard = player(1, "Will Reichard", "K", "K", 11.4)
    jets = player(2, "Jets D/ST", "D/ST", "D/ST", 9.1, weekly=11.4, opponent="NE")
    row = {
        "player_id": 3,
        "name": "Matt Gay",
        "position": "K",
        "suggested_drop": {
            "player_id": 2,
            "name": "Jets D/ST",
            "position": "D/ST",
            "projected_avg_points": 9.1,
        },
    }
    emergency = {"hole": {"player_id": 1, "position": "K", "slot": "K"}}

    drop = _emergency_safe_drop(row, snapshot([reichard, jets]), emergency)

    assert drop["player_id"] == 1
    assert drop["name"] == "Will Reichard"


def test_emergency_wr_repair_never_drops_unrelated_active_starter():
    garrett = player(10, "Garrett Wilson", "WR", "WR", 19.9, weekly=19.8, opponent="NE")
    kincaid = player(11, "Dalton Kincaid", "TE", "BE", 10.5, weekly=10.9, opponent="LV")
    row = {
        "player_id": 12,
        "name": "DeVonta Smith",
        "position": "WR",
        "suggested_drop": {
            "player_id": 10,
            "name": "Garrett Wilson",
            "position": "WR",
            "projected_avg_points": 19.9,
        },
    }
    emergency = {"hole": {"player_id": 13, "position": "WR", "slot": "WR"}}

    drop = _emergency_safe_drop(row, snapshot([garrett, kincaid]), emergency)

    assert drop["player_id"] == 11
    assert drop["name"] == "Dalton Kincaid"


def test_emergency_drop_skips_game_locked_bench_player():
    locked = player(20, "Locked Bench", "D/ST", "BE", 5.0, weekly=12, points=12)
    open_bench = player(21, "Open Bench", "TE", "BE", 11.0, weekly=9, opponent="LV")
    row = {
        "player_id": 22,
        "name": "Emergency WR",
        "position": "WR",
        "suggested_drop": {
            "player_id": 20,
            "name": "Locked Bench",
            "position": "D/ST",
            "projected_avg_points": 5.0,
        },
    }
    emergency = {"hole": {"player_id": 23, "position": "WR", "slot": "WR"}}

    drop = _emergency_safe_drop(row, snapshot([locked, open_bench]), emergency)

    assert drop["player_id"] == 21
