# BTC race bot: EMA(45)/EMA(120) trend-follower, long only.
# Buys CBBTC with a fifth of the cash when the fast EMA crosses above the
# slow EMA; sells the whole position when the slow EMA crosses back above the
# fast, on a 60 bps take-profit from the entry, or on a 20 bps trailing stop
# from the highest close since entry. One position at a time.
# Fifth size is deliberate: a full-size round trip pays about 26 bps in fees,
# slippage and price impact, and price impact grows with size, so a small
# trade keeps the round-trip cost low enough for the slow trend-follower's
# edge to survive it. The dev window drifts down 4.9% with small bounces;
# the neighbouring parameter sets (fast 45-50, slow 120, trail 20-25 bps,
# take-profit 60-80 bps, fifth to quarter size) all end the dev window
# slightly positive, so this is a robust region, not a tuned point.
# Speaks agent-fun/bars-replay/v1 through the vendored SDK shim: the harness
# sends hello, then one batch (a bar) at a time, and the bot answers each batch
# with its orders. Deterministic: no clock, no randomness, no network, no
# files outside the repository; the same bars give the same orders.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
FAST = 45
SLOW = 120
TRAIL_BPS = 20
TP_BPS = 60
SIZE_NUM = 1  # buy with SIZE_NUM/SIZE_DEN of the cash (a fifth)
SIZE_DEN = 5
MAX_SLIP_BPS = 100
MIN_NOTIONAL = 1_000_000  # 1 USDC in quote units


class Ema:
    """One EMA: the mean of its first span of closes, then 2/(span+1) steps."""

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def push(self, close):
        if self.value is not None:
            self.value += (2.0 / (self.span + 1)) * (close - self.value)
            return
        self.warm.append(close)
        if len(self.warm) == self.span:
            self.value = sum(self.warm) / self.span


fast = Ema(FAST)
slow = Ema(SLOW)
prev_gap = None  # fast - slow after the previous bar
entry = None  # entry price in bar units (x1e5), from the position's cost
peak = None  # highest close since entry


def on_batch(state, batch):
    global prev_gap, entry, peak
    bar = state.latest.get(SYMBOL)
    if bar is None:
        return []
    close = int(bar["c"])
    fast.push(close)
    slow.push(close)
    if fast.value is None or slow.value is None:
        return []
    gap = fast.value - slow.value
    if state.warming_up:
        prev_gap = gap
        return []
    holding = SYMBOL in state.positions
    if not holding:
        entry = None
        peak = None
        if prev_gap is not None and prev_gap <= 0 and gap > 0:
            prev_gap = gap
            amount = state.cash * SIZE_NUM // SIZE_DEN
            if amount >= MIN_NOTIONAL:
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": amount,
                         "max_slippage_bps": MAX_SLIP_BPS}]
        prev_gap = gap
        return []
    pos = state.positions[SYMBOL]
    if entry is None:
        # cost (quote units) / qty -> price in bar units: cost * 1e7 // qty
        entry = pos.cost * 10 ** 7 // pos.qty
        peak = close
    peak = max(peak, close)
    sell = False
    if prev_gap is not None and prev_gap >= 0 and gap < 0:
        sell = True  # slow EMA crossed above fast
    if close * 10000 >= entry * (10000 + TP_BPS):
        sell = True  # take-profit 60 bps over entry
    if close * 10000 < peak * (10000 - TRAIL_BPS):
        sell = True  # trailing stop 20 bps under the peak
    prev_gap = gap
    if sell:
        entry = None
        peak = None
        return [{"side": "sell", "symbol": SYMBOL, "qty": pos.qty,
                 "max_slippage_bps": MAX_SLIP_BPS}]
    return []


makefun_bars.run(on_batch)
