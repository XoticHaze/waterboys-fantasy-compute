# ACTUAL Poolside Laguna XS 2.1 synthetic model-generated code, not assistant-authored code
# Fixed public synthetic task BOUNDED_CLAMP_02; provider evidence run 41368669180
# 30/30 withheld checks passed in AST-only interpreter; no arbitrary model code executed
# NOT a production CommandCenter patch or authorization
def clamp_window(value, low, high, fallback):
    if low > high:
        return fallback
    if value < low:
        return low
    if value > high:
        return high
    return value
