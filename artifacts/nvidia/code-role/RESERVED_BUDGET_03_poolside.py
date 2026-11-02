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
