# WaterBoys Canonical Operator Runner

The canonical state-refresh runner is the GitHub Actions workflow:

- workflow: `.github/workflows/snapshot.yml`
- fire file: `rendezvous/fire/waterboys-snapshot-r1`
- private output: `XoticHaze/waterboys-fantasy-ops/state/latest.json`
- compact output: `XoticHaze/waterboys-fantasy-ops/state/brief.json`
- history: `XoticHaze/waterboys-fantasy-ops/history/snapshots/`

## Manual refresh

A controller/agent with GitHub write access should update the fire file with a fresh nonce, for example:

```json
{
  "schema": "waterboys.fire.v1",
  "action": "snapshot",
  "nonce": "decision-refresh-<unique-value>"
}
```

Commit that change to `main`. The push-path trigger launches `WaterBoys Snapshot R1`.

Do not place credentials or private league data in the fire file.

## Scheduled refresh

The workflow runs every four hours in addition to manual refreshes.

## Acceptance

A refresh is accepted only when:

1. `WaterBoys Snapshot R1` concludes successfully.
2. private `state/latest.json` has a new `collected_at`;
3. private `state/brief.json` is regenerated from the same run;
4. privacy flags remain false for credentials/tokens/cookies;
5. expected league/team-count gates pass.

For time-sensitive management decisions, read `state/brief.json` first, then drill into `state/latest.json` as needed.

## Security boundary

The public workflow gets short-lived GitHub OIDC identity. The Cloudflare broker verifies exact repo/ref/workflow/run identity before returning runtime material or accepting a snapshot. ESPN session material and private-repo write authority remain Cloudflare Worker secrets.

Live ESPN writes are separate from this runner and remain policy/canary gated.
