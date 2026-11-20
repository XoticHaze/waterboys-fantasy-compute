def quote_price_cents(minutes, hourly_cents, travel_cents, supplies_cents, overhead_bps, margin_bps):
    if minutes < 0 or hourly_cents < 0 or travel_cents < 0 or supplies_cents < 0 or overhead_bps < 0 or margin_bps < 0:
        return None
    if overhead_bps > 10000:
        return None
    if margin_bps >= 10000:
        return None
    labor = (minutes * hourly_cents + 59) // 60
    base = labor + travel_cents + supplies_cents
    overhead = (base * overhead_bps + 9999) // 10000
    total_cost = base + overhead
    if total_cost == 0:
        return None
    quote = (total_cost * 10000 + (10000 - margin_bps) - 1) // (10000 - margin_bps)
    return quote
