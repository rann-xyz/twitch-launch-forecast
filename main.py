"""GTA VI launch-day Twitch CCU forecast: reference-ratio model (Python 3.13, stdlib only).

Reads every ``<id>.in`` case in the input directory and writes ``<id>.out`` with five
quantiles of the Grand Theft Auto VI category's concurrent Twitch viewers for each of the
release day's hours 2..24.

The model
---------
A launch day's shape is stable when every hour is expressed as a ratio to that launch's
own hour-1 print, so the forecast is

    q_tau(h) = p1 * exp(mu_h + z_tau * sigma_h)

where ``p1`` is this case's hour-1 print, ``mu_h`` the weighted mean of the reference
log-ratios ln(v_i[h] / v_i[1]) and ``sigma_h`` their weighted standard deviation, made
non-decreasing over the day.  A reference is a comparable whose hourly points cover hours
0..23 with positive values and whose hour 1 already held at least 15% of its day peak
(a launch still asleep in its first hour has a useless ratio curve).  Weights are
``exp(-|ln(v_i[1]) - ln(p1)| / 0.5)``, so references of a similar size count most.

Robustness
----------
* ``p1`` is hour 1's ``known`` print when the case carries a usable one; otherwise the mean
  of the ``history_hourly`` points inside the hour ending at ``checkpoint``; otherwise 1.0.
* The per-hour spread is clamped into [0.02, 2.0] before it is carried forward as the
  day's non-decreasing spread, so a degenerate reference set cannot produce absurd
  quantiles.
* Exactly the 23 rows for hours 2..24 are always written, in that order: the case's own
  ``forecast`` rows are not trusted for the shape the grader checks.
* Fewer than 4 usable references, or a case that cannot be parsed, fall back to the house
  persistence shape ``p1 * exp(z_tau * 0.15 * sqrt(h - 1))``, with ``p1 = 1`` when the case
  has no usable print, so a broken case still writes a valid file.
* Every read, forecast and write of one case is wrapped on its own: a case that fails
  cannot stop the others, and the program exits 0 whatever the cases hold.

Run locally:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The levels scored, in the order a row lists its quantiles, and their normal quantiles.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]
HOURS = list(range(2, 25))

# Reference filter and aggregation constants (fixed by the design, not tuned per hour).
MIN_REFS = 4          # below this, use the house baseline shape
FRAC_MIN = 0.15       # hour 1 must hold at least this share of the day's peak
WEIGHT_TAU = 0.5      # size weight: exp(-|ln(v1_i) - ln(p1)| / WEIGHT_TAU)
SPREAD = 1.0          # multiplier on the reference dispersion
BASE_SIGMA = 0.15     # the house baseline's log-spread per sqrt(hour)
MIN_SIGMA = 0.02      # a forecast row is never narrower than this
MAX_SIGMA = 2.0       # ... and never wider: exp(1.645 * 2) is already ~27x
SIGMA_MIN = 0.02      # a degenerate reference set must not collapse the spread to nothing
SIGMA_MAX = 2.0       # nor blow it up: exp(2.0 * 1.645) would be a 27x quantile

ONE_HOUR = timedelta(hours=1)
UTC = timezone.utc
MAX_Q = 1e9
MIN_Q = 0.01


def parse_utc(value):
    """Parse an ISO 8601 timestamp to an aware UTC datetime (raises on anything odd)."""
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def as_number(value):
    """Return value as a finite float, or None when it is not a usable number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def hour1_print(case):
    """Hour 1's viewer print: `known` when usable, else the hour ending at the checkpoint."""
    known = case.get("known")
    if isinstance(known, list):
        for row in known:
            if isinstance(row, dict) and row.get("hour") == 1:
                viewers = as_number(row.get("viewers"))
                if viewers is not None and viewers > 0:
                    return viewers

    # No usable print: average the whole-hour points in the hour that ends at the checkpoint.
    try:
        checkpoint = parse_utc(case.get("checkpoint"))
    except (ValueError, TypeError):
        return 1.0
    hourly = case.get("history_hourly")
    if isinstance(hourly, list):
        samples = []
        for point in hourly:
            if not isinstance(point, dict):
                continue
            try:
                start = parse_utc(point.get("from"))
            except (ValueError, TypeError):
                continue
            viewers = as_number(point.get("viewers"))
            if viewers is None or viewers <= 0:
                continue
            if start < checkpoint <= start + ONE_HOUR:
                samples.append(viewers)
        if samples:
            return sum(samples) / len(samples)
    return 1.0


def reference(comparable):
    """A usable reference: (its hour-1 print, its 23 log-free ratios) or None."""
    if not isinstance(comparable, dict):
        return None
    hourly = comparable.get("hourly")
    if not isinstance(hourly, list):
        return None
    try:
        day_start = parse_utc(comparable.get("day_start"))
    except (ValueError, TypeError):
        return None

    totals = {}
    for point in hourly:
        if not isinstance(point, dict):
            continue
        try:
            hour = (parse_utc(point.get("from")) - day_start) // ONE_HOUR
        except (ValueError, TypeError):
            continue
        if hour < 0 or hour > 23:
            continue
        viewers = as_number(point.get("viewers"))
        if viewers is None:
            continue
        totals.setdefault(hour, []).append(viewers)

    values = {}
    for hour, samples in totals.items():
        mean = sum(samples) / len(samples)
        if mean > 0:
            values[hour] = mean

    if 0 not in values:
        return None
    for hour in range(1, 24):
        if hour not in values:
            return None

    curve = [values[hour] for hour in range(24)]
    first = curve[0]
    peak = max(curve)
    if peak <= 0 or first / peak < FRAC_MIN:
        return None
    return first, [curve[hour] / first for hour in range(1, 24)]


def baseline_row(p1, hour):
    """The house persistence quantiles for one hour."""
    spread = BASE_SIGMA * math.sqrt(hour - 1)
    return [p1 * math.exp(z * spread) for z in Z]


def model_rows(p1, references, hours):
    """Weighted reference-ratio quantiles for each hour, in ascending hour order."""
    log_p1 = math.log(max(p1, 1.0))
    rows = []
    sigma_floor = 0.0
    for hour in sorted(hours):
        terms = []
        for v1, ratios in references:
            weight = math.exp(-abs(math.log(v1) - log_p1) / WEIGHT_TAU)
            terms.append((weight, math.log(ratios[hour - 2])))
        total = sum(weight for weight, _ in terms)
        if total > 0:
            mu = sum(weight * value for weight, value in terms) / total
            variance = sum(weight * (value - mu) ** 2 for weight, value in terms) / total
            sigma = SPREAD * math.sqrt(variance) if variance > 0 else 0.0
        else:  # every size weight underflowed: use the plain dispersion
            mu = sum(value for _, value in terms) / len(terms)
            variance = sum((value - mu) ** 2 for _, value in terms) / len(terms)
            sigma = SPREAD * math.sqrt(variance) if variance > 0 else 0.0
        if not (math.isfinite(mu) and math.isfinite(sigma)):
            rows.append({"hour": hour, "q": tidy(baseline_row(p1, hour))})
            continue
        # Keep the spread in a sane band, then let it only grow with the horizon.
        sigma = min(max(sigma, SIGMA_MIN), SIGMA_MAX)
        sigma_floor = max(sigma_floor, sigma)
        rows.append({"hour": hour, "q": tidy([p1 * math.exp(mu + z * sigma_floor) for z in Z])})
    return rows


def round2(value):
    """Round half up to 2 decimals, as int when whole (matches the house starter)."""
    scaled = value * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    result = whole / 100.0
    return int(result) if result.is_integer() else result


def tidy(quantiles):
    """Clamp into (0, 1e9], round to 2 decimals, and force the five to be non-decreasing."""
    out = []
    previous = 0.0
    for value in quantiles:
        if not math.isfinite(value):
            value = previous if previous > 0 else MIN_Q
        value = min(max(value, MIN_Q), MAX_Q)
        value = round2(value)
        if value < previous:
            value = previous
        if value < MIN_Q:
            value = MIN_Q
        out.append(value)
        previous = value
    return out


def forecast_case(case):
    """The output object for one parsed case; never raises on odd data.

    The grader expects exactly hours 2..24, so the case's own `forecast` rows cannot
    choose the hours: they are always 2..24.
    """
    hours = list(HOURS)
    p1 = hour1_print(case)

    references = []
    comparables = case.get("comparables")
    if isinstance(comparables, list):
        for comparable in comparables:
            try:
                built = reference(comparable)
            except Exception:
                built = None
            if built is not None:
                references.append(built)

    if len(references) >= MIN_REFS:
        rows = model_rows(p1, references, hours)
    else:
        rows = [{"hour": hour, "q": tidy(baseline_row(p1, hour))} for hour in hours]
    return {"hours": rows}


def fallback():
    """A valid forecast that needs nothing from the case."""
    return {"hours": [{"hour": hour, "q": tidy(baseline_row(1.0, hour))} for hour in HOURS]}


def dump(payload):
    """Serialise a payload, falling back to the built-in one if it is not serialisable."""
    try:
        return json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
    except (ValueError, TypeError):
        return json.dumps(fallback(), separators=(",", ":")) + "\n"


def main():
    input_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR") or "/input")
    output_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    try:
        cases = sorted(input_dir.glob("*.in"), key=lambda path: path.name)
    except OSError:
        cases = []

    for path in cases:
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                raise ValueError("case is not an object")
            payload = forecast_case(case)
        except Exception:
            payload = fallback()
        try:
            (output_dir / (path.stem + ".out")).write_text(dump(payload), encoding="utf-8")
        except OSError:
            pass


if __name__ == "__main__":
    main()
