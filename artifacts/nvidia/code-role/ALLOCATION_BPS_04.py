# ACTUAL Poolside Laguna XS 2.1 synthetic model-generated code, not assistant-authored code
# Fixed public synthetic task ALLOCATION_BPS_04; provider evidence run 41369461560
# 30/30 withheld checks passed in AST-only interpreter; no arbitrary model code executed
# NOT a production CommandCenter patch or authorization
def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):
    if equity <= 0 or risk_bps <= 0 or risk_bps > 10000 or cap_usd <= 0 or minimum_usd <= 0 or cap_usd < minimum_usd:
        return None
    allowed = min(cap_usd, (equity * risk_bps) // 10000)
    if allowed < minimum_usd:
        return None
    return allowed
