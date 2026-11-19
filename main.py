"""GTA VI trophy earn-rate forecaster, entry for make.fun gta6-trophy-rarity-forecast-01.

Standard library only, deterministic, offline. For each trophy the model combines
the last observed rate with a damped trend fitted over the recent reads, then
assigns logit-normal quantiles whose spread grows with the horizon and with the
fit's residual noise. No stored answers, no network, no model calls.
"""
import json
import math
import os
import sys
from pathlib import Path

# The grader runs with -P, so add this file's directory to import from it if needed.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
RELEASE = "2026-11-19T00:00:00Z"


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
    move = slope * gap * 0.55
    move = clamp(move, -1.5, 3.0)
    median_y = last_y + move

    # Honest spread: widening with horizon, noise in the fit, and trophy rarity.
    spread = 0.35 + 0.55 * math.sqrt(days) + 0.45 * residual
    if last_rate < 2.0:
        spread += 0.25
    spread = clamp(spread, 0.45, 3.2)
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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        result = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(f"wrote {path.stem}.out ({len(result['trophies'])} trophies)")


if __name__ == "__main__":
    main()
