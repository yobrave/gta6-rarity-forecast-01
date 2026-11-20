"""Forecast GTA VI trophy earn rates at a case's target, from the case's read history.

Launch-night reads come from a tiny first cohort and end at Exophase's first
refresh (the tracked base multiplied many times over and every displayed rate
moved with it), so they describe a different regime from everything after.
This program splits the history at the first player-count jump, then treats
each trophy's scoring logit as a random walk with drift over the post-refresh
states: the level is anchored on the latest observed state (the most
informative single read), and the drift is a recency-weighted slope against
ln(1 + hours) shrunk toward the pooled slope of live trophies. Quantile
spread comes from the weighted fit residual, the slope's standard error and a
model-risk floor honest about a multi-day extrapolation. The pinball loss is
a proper scoring rule, so the quantiles are the ones this model actually
believes.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.645, -0.674, 0.0, 0.674, 1.645)
LOGIT_FLOOR = math.log(0.01 / 99.99)
LOGIT_CEIL = math.log(99.99 / 0.01)
B_CLAMP = (-1.5, 1.0)
SIGMA_FLOOR = 0.80
SIGMA_CAP = 1.50
WEIGHT_TAU_H = 24.0


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hours_between(later, earlier):
    return (later - earlier).total_seconds() / 3600.0


def clamp_logit(pct):
    if pct <= 0.01:
        return LOGIT_FLOOR
    if pct >= 99.99:
        return LOGIT_CEIL
    return math.log(pct / (100.0 - pct))


def from_logit(x):
    if x >= 0:
        return 100.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return 100.0 * e / (1.0 + e)


def round4(x):
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value == int(value) else value


def wols(points):
    """Recency-weighted OLS on [(x, rate)]: returns (slope, rms residual, se_slope, sxx_w)."""
    xs = [x for x, _r in points]
    ys = [clamp_logit(r) for _x, r in points]
    ts = [math.exp(x) - 1.0 for x in xs]
    t_last = ts[-1]
    ws = [math.exp(-(t_last - t) / WEIGHT_TAU_H) for t in ts]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    if sxx <= 1e-9:
        return 0.0, 0.0, 0.0, sxx
    sxy = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    b = sxy / sxx
    resid = [y - (my + b * (x - mx)) for x, y in zip(xs, ys)]
    s = math.sqrt(sum(w * r * r for w, r in zip(ws, resid)) / sw)
    se_b = s / math.sqrt(sxx)
    return b, s, se_b, sxx


def distinct_states(history):
    states = []
    for read in history:
        rates = read.get("rates")
        if rates is None:
            continue
        tracked = read.get("players_tracked") or 0
        key = (tracked, tuple(rates))
        if states and states[-1][1] == key:
            continue
        states.append((parse_ts(read["at"]), key))
    return states


def forecast_trophy(points, x_target, b_pool):
    """points: [(x, displayed rate)] in ascending x; returns (median logit, sigma, q list).

    Level anchored on the latest state; drift = recency-weighted slope shrunk
    toward the pool of live-trophy slopes.
    """
    displayed = [r for _x, r in points]
    if displayed and min(displayed) >= 99.99:
        return LOGIT_CEIL, 0.0, [99.99, 100, 100, 100, 100]
    if displayed and max(displayed) <= 0.01:
        return LOGIT_FLOOR, 0.0, [0.01, 0.01, 0.01, 0.01, 0.011]

    k = len(points)
    x_last = points[-1][0]
    y_last = clamp_logit(points[-1][1])
    dx = x_target - x_last

    if k >= 2:
        b, s, se_b, sxx = wols(points)
        weight = k / (k + 2.0)
        b = weight * b + (1.0 - weight) * b_pool
        b = min(max(b, B_CLAMP[0]), B_CLAMP[1])
        median = y_last + b * dx
        slope_term = se_b * abs(dx)
        if k >= 3:
            sigma = math.sqrt(s * s + slope_term * slope_term + SIGMA_FLOOR ** 2)
        else:
            sigma = math.sqrt(max(slope_term, 0.35) ** 2 + SIGMA_FLOOR ** 2)
    else:
        b = min(max(b_pool * 0.5, B_CLAMP[0]), B_CLAMP[1])
        median = y_last + b * dx
        sigma = min(SIGMA_CAP, max(0.15, 0.8 * abs(dx)))

    sigma = min(max(sigma, SIGMA_FLOOR), SIGMA_CAP)
    qs = []
    last = 0.0
    for z in Z:
        q = min(99.99, max(0.01, from_logit(median + z * sigma)))
        q = round4(q)
        if q < last:
            q = last
        last = q
        qs.append(q)
    return median, sigma, qs


def forecast_case(case):
    states = distinct_states(case.get("history") or [])
    if not states:
        raise ValueError("case has no readable history")
    base_tracked = states[0][1][0]
    cut = next((i for i, (_at, (tracked, _r)) in enumerate(states)
                if base_tracked and tracked >= 2 * base_tracked), None)
    post = states[cut:] if cut is not None else states
    t0 = post[0][0]
    x_target = math.log(1.0 + max(hours_between(parse_ts(case["target"]), t0), 0.0))
    xs = [math.log(1.0 + max(hours_between(at, t0), 0.0)) for at, _key in post]

    points_per_trophy = []
    for i in range(len(case["trophies"])):
        pts = [(x, post[j][1][1][i]) for j, x in enumerate(xs)
               if post[j][1][1][i] is not None]
        points_per_trophy.append(pts)

    slopes = []
    for pts in points_per_trophy:
        displayed = [r for _x, r in pts]
        if len(pts) >= 3 and min(displayed) > 0.01 and max(displayed) < 99.99:
            slopes.append(wols(pts)[0])
    b_pool = sorted(slopes)[len(slopes) // 2] if slopes else 0.0

    rows = []
    for trophy, pts in zip(case["trophies"], points_per_trophy):
        _median, _sigma, qs = forecast_trophy(pts, x_target, b_pool)
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if tuple(case["levels"]) != LEVELS:
            raise ValueError("%s asks for levels %s" % (path.name, case["levels"]))
        forecast = forecast_case(case)
        payload = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / (path.stem + ".out")).write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
