# ACTUAL MiniMax M3.1 Flash synthetic model-generated code, not assistant-authored code
# Fixed public synthetic task RETRY_DEADLINE_01; provider evidence run 41368770454
# 30/30 withheld checks passed in AST-only interpreter; no arbitrary model code executed
# NOT a production CommandCenter patch or authorization
def retry_delay_ms(attempt, max_attempts, base_ms, cap_ms):
    if attempt <= 0 or max_attempts <= 0 or attempt >= max_attempts or base_ms <= 0 or cap_ms <= 0:
        return None
    return min(cap_ms, base_ms * (2 ** (attempt - 1)))
