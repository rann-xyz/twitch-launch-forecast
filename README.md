# twitch-launch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rann-xyz/twitch-launch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rann-xyz/twitch-launch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Entry for the make.fun bounty **`gta6-twitch-ccu-forecast-01`**: forecast the Grand Theft
Auto VI category's concurrent Twitch viewers in each hour of its release day,
2026-11-19 (UTC), hours 2 to 24, from the release day's first hour onward.

Each case is one JSON file `<id>.in`; the program writes `<id>.out` with five quantiles
(0.05, 0.25, 0.5, 0.75, 0.95) per hour, and is scored by mean pinball loss on the log
scale. It runs offline in a sandbox: Python 3.13, standard library only.

## Algorithm

Every hour of a past big launch is expressed as a ratio to that launch's own hour-1
print. A comparable is usable when its hourly points cover hours 0..23 with positive
values and its hour 1 already held at least 15% of the day's peak (a launch still asleep
in its first hour has a ratio curve that says nothing about a launch that is already
live). For each forecast hour the usable references are averaged in log space, each
weighted by `exp(-|ln(v1_i) - ln(p1)| / 0.5)` so launches of a similar size count most:
`mu_h` is the weighted mean of `ln(v_i[h] / v_i[1])` and `sigma_h` their weighted standard
deviation, clamped to [0.02, 2.0] and raised to be non-decreasing over the day, so
`q_tau(h) = p1 * exp(mu_h + z_tau * sigma_h)` with `p1` the case's hour-1 print: its
`known` row when usable, else the mean of the `history_hourly` points in the hour ending
at `checkpoint`, else 1. Fallbacks, each still writing a valid file: fewer than 4 usable
references (or a case that cannot be parsed) use the house persistence shape
`p1 * exp(z_tau * 0.15 * sqrt(h-1))`, hours other than 2..24 in `forecast` are ignored,
and one bad case never stops the others.

## Run it locally

    mkdir -p out
    MAKEFUN_INPUT_DIR=/home/userland/makefun/fc-01-kit/gta6-twitch-ccu-forecast-01-kit/input \
    MAKEFUN_OUTPUT_DIR=out python3 main.py

With neither variable set it reads `/input` and writes `/output`, as the grader does. It
reads every `*.in` file in name order and writes one `<id>.out` per case.

## Output

    {"hours":[{"hour":2,"q":[78133.6,90384.26,100000,110638.73,127985.91]}, ...]}

Exactly 23 rows, hours 2..24, each with five finite, positive, non-decreasing numbers at
most 1e9; the file is well under the 65,536-byte limit. Output is deterministic: no
randomness and no clock, so two runs are byte-identical.

`tools/check_outputs.py <dir>` validates a directory of outputs against that shape.

## Validation done here

All four practice cases run in about 0.8 s together, a single-case run (as the grader
does) in about 1 s including interpreter start-up — well under the 8 s cap. Runs are
byte-identical and every output passes the shape checker. The offline proxy score is a
leave-one-out over the 26 usable comparables, each forecast from the others and scored
against its own hours: mean pinball loss about 0.202, against 0.284 for the persistence
shape. It is a proxy only — the practice cases carry no hours 2..24 answer of their own.

## License

MIT, see `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=602xpbd6&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
