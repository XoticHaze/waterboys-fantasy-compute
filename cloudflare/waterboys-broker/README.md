# WaterBoys broker

The Worker is the private authority boundary between public GitHub-hosted compute and the private WaterBoys ops repository.

Required Cloudflare Worker secrets:

- `OPS_GITHUB_TOKEN`: fine-grained GitHub token limited to `XoticHaze/waterboys-fantasy-ops` contents read/write.
- `ESPN_S2`: ESPN private-league session cookie.
- `ESPN_SWID`: ESPN SWID cookie.

Do not store these values in this repository or in WaterBoys GitHub Actions secrets.

The Worker accepts only GitHub OIDC identities from the exact `main` workflows declared in `src/index.js`.
