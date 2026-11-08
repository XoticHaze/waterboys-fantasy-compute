from __future__ import annotations

"""Fail closed on ESPNs terminal knockout-team state before ANY write."""

from typing import Any


def team_write_block_reason(snapshot: dict[str, Any]) -> str | None:
    """Return None only for an identifiable surviving team with an active roster.

    A missing or inconsistent roster/survival feed must not be interpreted as an
    emergency waiver opportunity. This is a write gate, not a scoring opinion.
    """
    team = snapshot.get("waterboys")
    survival = snapshot.get("survival")
    if not isinstance(team, dict) or not isinstance(survival, dict):
        return "team_or_survival_state_missing"

    team_id = team.get("team_id")
    if not isinstance(team_id, int) or isinstance(team_id, bool):
        return "team_identity_missing"

    eliminated = survival.get("eliminated_teams")
    if not isinstance(eliminated, list):
        return "elimination_status_missing"
    if any(
        isinstance(row, dict) and row.get("team_id") == team_id
        for row in eliminated
    ):
        return "team_eliminated"

    roster = team.get("roster")
    if not isinstance(roster, list):
        return "team_roster_unavailable"
    if not roster or team.get("roster_count") == 0:
        return "team_roster_empty"

    rankings = survival.get("current_week_ranking")
    if isinstance(rankings, list) and rankings and not any(
        isinstance(row, dict) and row.get("team_id") == team_id
        for row in rankings
    ):
        return "team_absent_from_survivor_ranking"

    return None
