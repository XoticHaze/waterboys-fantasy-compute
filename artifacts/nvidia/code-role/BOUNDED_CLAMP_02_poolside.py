def clamp_window(value, low, high, fallback):
    if low > high:
        return fallback
    if value < low:
        return low
    if value > high:
        return high
    return value
