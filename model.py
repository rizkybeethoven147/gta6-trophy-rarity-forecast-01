"""Refactored GTA VI trophy earn-rate forecaster.

Standard library only, deterministic, offline. The model combines the last
observed rate with a damped trend fitted over recent reads, shifts the median
by a per-tier prior, and assigns logit-normal quantiles whose spread grows with
the horizon, the fit's residual noise, and trophy rarity.
"""
import math

RELEASE = "2026-11-19T00:00:00Z"
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Logit-scale shift applied to a trophy's median forecast by tier.
TIER_PRIOR = {
    "platinum": -0.15,
    "gold": -0.05,
    "silver": 0.0,
    "bronze": 0.05,
}


def hours(text):
    """UTC timestamp to hours since the game's release."""
    from datetime import datetime
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    r = datetime.fromisoformat(RELEASE.replace("Z", "+00:00"))
    return (t - r).total_seconds() / 3600.0


def clamp(x, low, high):
    return min(high, max(low, x))


def logit(pct):
    p = clamp(pct, 0.01, 99.99) / 100.0
    return math.log(p / (1.0 - p))


def expit(x):
    return 100.0 / (1.0 + math.exp(-x))


def round4(x):
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value.is_integer() else value


def _tier_key(tier):
    """Normalize a tier value for lookup; unknown values map to no prior."""
    return str(tier).strip().lower()


def tier_prior(trophy):
    """Logit-scale median shift for a trophy: rare tiers shift downward."""
    return TIER_PRIOR.get(_tier_key(trophy.get("tier", "")), 0.0)


def calibrated_spread(last_rate, days, residual, tier):
    """Quantile spread, widened by horizon, fit noise, and trophy rarity.

    Rare tiers (platinum/gold) carry extra uncertainty; common tiers do not.
    The very low observed rate of a rare trophy also widens the spread.
    """
    spread = 0.35 + 0.55 * math.sqrt(max(0.0, days)) + 0.45 * residual
    if last_rate < 2.0:
        spread += 0.25
    rarity = max(0.0, -TIER_PRIOR.get(_tier_key(tier), 0.0))
    spread += 1.5 * rarity
    return clamp(spread, 0.45, 3.2)


def fit_trend(points):
    """Least-squares slope and residual std of logit(rate) against hours."""
    n = len(points)
    if n < 3:
        return 0.0, 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 1e-9:
        return 0.0, 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    resid = [y - (my + slope * (x - mx)) for x, y in zip(xs, ys)]
    var = sum(r * r for r in resid) / n
    return slope, math.sqrt(var)


def forecast_trophy(case, idx, target_h):
    trophy = case["trophies"][idx]
    tier = trophy.get("tier", "")
    history = case["history"]
    recent = []
    for read in history:
        rate = read["rates"][idx]
        if rate is None:
            continue
        t = hours(read["at"])
        if t >= -48.0:
            recent.append((t, logit(rate)))
    if not recent:
        recent = [(hours(history[-1]["at"]), logit(0.5))]

    last_h, last_y = recent[-1]
    last_rate = expit(last_y)
    if last_rate >= 99.995:
        return [100.0] * 5

    # Reads in the last 24 hours carry the current pace; older reads stay as context.
    window = [p for p in recent if p[0] >= last_h - 24.0]
    if len(window) < 3:
        window = recent[-6:]
    slope, residual = fit_trend(window)

    gap = max(0.0, target_h - last_h)
    days = gap / 24.0
    # Damp the fitted pace: a launch-night burst rarely continues at full speed.
    move = clamp(slope * gap * 0.55, -1.5, 3.0)
    median_y = last_y + move + tier_prior(trophy)

    spread = calibrated_spread(last_rate, days, residual, tier)
    return [round4(clamp(expit(median_y + z * spread), 0.0, 100.0)) for z in Z]


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name}: unexpected levels {case.get('levels')}")
    if not case.get("history"):
        raise ValueError(f"{name}: no history")
    target_h = hours(case["target"])
    rows = []
    for idx, trophy in enumerate(case["trophies"]):
        rows.append({"id": trophy["id"], "q": forecast_trophy(case, idx, target_h)})
    return {"trophies": rows}
