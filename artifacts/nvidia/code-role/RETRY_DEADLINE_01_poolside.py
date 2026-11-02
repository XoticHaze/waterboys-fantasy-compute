def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts or base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))
