# ACTUAL Poolside Laguna XS 2.1 synthetic model-generated code, not assistant-authored code
# Fixed public synthetic task STALE_HEARTBEAT_05; provider evidence run 41369461560
# 30/30 withheld checks passed in AST-only interpreter; no arbitrary model code executed
# NOT a production CommandCenter patch or authorization
def staleness_status(now_ms, last_ms, warn_ms, expire_ms):
    if now_ms < 0 or last_ms < 0 or now_ms < last_ms or warn_ms <= 0 or expire_ms <= warn_ms:
        return -1
    elapsed = now_ms - last_ms
    if elapsed < warn_ms:
        return 0
    if elapsed < expire_ms:
        return 1
    return 2
