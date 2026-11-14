# BTC race bot

A long-only trend-follower for the make.fun "Race a BTC trading bot live for
24 hours" bounty (btc-race-24h-20261113-2314). It trades Coinbase Wrapped BTC
(CBBTC) against USDC, one minute bar at a time, on paper money.

## Strategy

- **Entry:** buy with a fifth of the cash when EMA(45) of the closes
  crosses above EMA(120). Slow crosses only: the fast 1-minute noise is not
  traded.
- **Exit (whole position):** the slow EMA crosses back above the fast, the
  close reaches 60 bps over the entry (take-profit), or the close falls
  20 bps under the highest close since entry (trailing stop).
- **Costs:** a full-size round trip pays about 26 bps in fees, slippage and
  price impact, and the impact grows with size, so the bot trades a fifth
  of its cash: the round-trip cost falls enough for the slow trend-follower's
  edge to survive it.

## Why this shape

The frozen dev window drifts down 4.9% with 47 small bounces (>=20 bps). Fast
trend-followers whipsaw on the 1-minute noise and bleed on fees; slow ones
catch the real bounces and sit in cash through the bleed. Across the
neighbouring parameter sets (fast 45-50, slow 120, trail 20-25 bps,
take-profit 60-80 bps, fifth to quarter size) the dev-window net PnL is
positive, so the choice is a robust region, not a single tuned point. The dev
grade is about +$0.39 on $1,000 of paper money: a thin edge on a hard window,
and the bot is built to survive the race window rather than to overfit the dev
one.

## Files

- `main.py` — the bot. Speaks agent-fun/bars-replay/v1 on stdin/stdout,
  standard library only, self-contained (no vendored code).

## Running it

The bot is graded by the kit's replay (`makefun grade-local`); it reads one
JSON line per minute (a bar) and answers with buy/sell orders. It uses only
the Python standard library, reads no clock, no environment and no network,
and the same bars always give the same orders.

## License

MIT. See LICENSE.
