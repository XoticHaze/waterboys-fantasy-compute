def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts or base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))

def clamp_window(value, low, high, fallback):
    if low > high:
        return fallback
    if value < low:
        return low
    if value > high:
        return high
    return value

def budget_remaining(limit, spent, reserved, floor):
    if limit < 0:
        return None
    if spent < 0:
        return None
    if reserved < 0:
        return None
    if floor < 0:
        return None
    free = limit - spent - reserved
    if free < floor:
        return None
    return free

def allocation_limit(equity, risk_bps, cap_usd, minimum_usd):
    if equity <= 0 or risk_bps <= 0 or risk_bps > 10000 or cap_usd <= 0 or minimum_usd <= 0 or cap_usd < minimum_usd:
        return None
    allowed = min(cap_usd, (equity * risk_bps) // 10000)
    if allowed < minimum_usd:
        return None
    return allowed

def staleness_status(now_ms, last_ms, warn_ms, expire_ms):
    if now_ms < 0 or last_ms < 0 or now_ms < last_ms or warn_ms <= 0 or expire_ms <= warn_ms:
        return -1
    elapsed = now_ms - last_ms
    if elapsed < warn_ms:
        return 0
    if elapsed < expire_ms:
        return 1
    return 2
