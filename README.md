# WaterBoys Fantasy Compute

Public, stateless compute surface for WaterBoys fantasy-football operations.

The repository is intentionally safe to inspect publicly. It contains no league credentials, private roster state, FAAB history, or private commands.

## Security boundary

GitHub-hosted Actions obtain a short-lived GitHub OIDC token. The WaterBoys Cloudflare Worker verifies the exact repository/ref/workflow identity before returning runtime material or accepting normalized state.

Canonical private state lives in `XoticHaze/waterboys-fantasy-ops`.

## Current authority

- Read collector: enabled after Cloudflare secrets/config are provisioned.
- ESPN writes: dry-run only by default.
- No dependency on MM-IBKR or CommandCenter execution queues.
