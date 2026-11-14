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
# Speaks agent-fun/bars-replay/v1 on stdin/stdout with the standard library
# alone: the harness sends hello, then one batch (a bar) at a time, and the
# bot answers each batch with its orders. Deterministic: no clock, no
# randomness, no network, no environment, no files outside the repository;
# the same bars give the same orders.
import json
import sys

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
next_id = 1  # client_ids o1, o2, ... never reused


def decide(cash, positions, latest, warming_up):
    """The orders for this batch (a bar). Returns a list of order dicts."""
    global prev_gap, entry, peak, next_id
    bar = latest.get(SYMBOL)
    if bar is None:
        return []
    close = int(bar["c"])
    fast.push(close)
    slow.push(close)
    if fast.value is None or slow.value is None:
        return []
    gap = fast.value - slow.value
    if warming_up:
        prev_gap = gap
        return []
    holding = SYMBOL in positions
    if not holding:
        entry = None
        peak = None
        if prev_gap is not None and prev_gap <= 0 and gap > 0:
            prev_gap = gap
            amount = cash * SIZE_NUM // SIZE_DEN
            if amount >= MIN_NOTIONAL:
                cid = "o%d" % next_id
                next_id += 1
                return [{"side": "buy", "client_id": cid, "symbol": SYMBOL,
                         "notional_quote_units": amount,
                         "max_slippage_bps": MAX_SLIP_BPS}]
        prev_gap = gap
        return []
    qty, cost = positions[SYMBOL]
    if entry is None:
        # cost (quote units) / qty -> price in bar units: cost * 1e7 // qty
        entry = cost * 10 ** 7 // qty
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
        cid = "o%d" % next_id
        next_id += 1
        return [{"side": "sell", "client_id": cid, "symbol": SYMBOL,
                 "qty": qty, "max_slippage_bps": MAX_SLIP_BPS}]
    return []


def main():
    cash = 0
    positions = {}
    latest = {}
    warmup_bars = 0
    seq = -1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "hello":
            warmup_bars = msg.get("warmup_bars", 0)
            cash = int(msg["capital"]["quote_units"])
            continue
        if kind == "batch":
            seq = msg["seq"]
            for bar in msg["bars"]:
                latest[bar["symbol"]] = bar
            account = msg["account"]
            cash = int(account["cash_quote_units"])
            positions = {p["symbol"]: (int(p["qty"]), int(p["cost_quote_units"]))
                         for p in account["positions"]}
            warming_up = warmup_bars > 0 and seq < warmup_bars
            orders = decide(cash, positions, latest, warming_up)
            reply = json.dumps({"type": "reply", "seq": seq, "orders": orders},
                               separators=(",", ":"))
            sys.stdout.write(reply + "\n")
            sys.stdout.flush()
        elif kind == "done":
            return


main()
