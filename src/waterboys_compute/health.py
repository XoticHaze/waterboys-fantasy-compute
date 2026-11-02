from __future__ import annotations

"""Report whether the expected hourly sniper actually published a receipt."""

from datetime import datetime, timezone


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except ValueError:
        return None


def sniper_cadence(previous_report: dict | None, now: str, expected_minutes: int = 60) -> dict:
    prior = _parse_timestamp((previous_report or {}).get("created_at"))
    current = _parse_timestamp(now)
    if not current or not prior:
        return {
            "status": "unknown_no_previous_report",
            "expected_interval_minutes": expected_minutes,
            "last_report_at": (previous_report or {}).get("created_at"),
            "observed_gap_minutes": None,
            "missed_expected_intervals": None,
        }
    observed = max(0, round((current - prior).total_seconds() / 60, 2))
    # GitHub's cron can be delayed. Allow 30 minutes before flagging overdue.
    late = observed > expected_minutes + 30
    return {
        "status": "overdue" if late else "on_schedule",
        "expected_interval_minutes": expected_minutes,
        "last_report_at": prior.isoformat(),
        "observed_gap_minutes": observed,
        "missed_expected_intervals": max(0, int(observed // expected_minutes) - 1),
    }
