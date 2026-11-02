# ACTUAL Poolside Laguna XS 2.1 synthetic model-generated code, not assistant-authored code
# Fixed public synthetic task RESERVED_BUDGET_03; provider evidence run 41369461560
# 30/30 withheld checks passed in AST-only interpreter; no arbitrary model code executed
# NOT a production CommandCenter patch or authorization
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
