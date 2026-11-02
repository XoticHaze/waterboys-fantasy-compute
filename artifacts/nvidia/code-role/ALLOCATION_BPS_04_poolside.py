def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):
    if equity <= 0 or risk_bps <= 0 or risk_bps > 10000 or cap_usd <= 0 or minimum_usd <= 0 or cap_usd < minimum_usd:
        return None
    allowed = min(cap_usd, (equity * risk_bps) // 10000)
    if allowed < minimum_usd:
        return None
    return allowed
