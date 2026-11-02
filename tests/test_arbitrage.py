import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arbitrage import Quote, find_opportunities  # noqa: E402


def q(sym, bid_ars, ask_ars, bid_usd, ask_usd, qty=1000):
    return Quote(sym, bid_ars, ask_ars, bid_usd, ask_usd, qty, qty, qty, qty)


def test_no_opportunity_when_mep_aligned():
    quotes = [q("AL30", 1000, 1002, 0.70, 0.7005), q("GD30", 1000, 1002, 0.70, 0.7005)]
    assert find_opportunities(quotes, fee_pct=0.15, min_profit_pct=0.3) == []


def test_detects_opportunity_and_direction():
    # AL30: MEP de compra bajo (barato conseguir USD); GD30: MEP de venta alto
    a = q("AL30", 1390, 1400, 1.0, 1.01)      # mep_compra = 1400
    b = q("GD30", 1450, 1460, 0.98, 0.99)     # mep_venta ~ 1464.6
    opps = find_opportunities([a, b], fee_pct=0.0, min_profit_pct=0.3)
    assert len(opps) == 1
    o = opps[0]
    assert (o["via_usd"], o["back_to_ars"]) == ("AL30", "GD30")
    assert o["net_pct"] > 4
    assert [l["side"] for l in o["legs"]] == ["buy", "sell", "buy", "sell"]
    assert [l["symbol"] for l in o["legs"]] == ["AL30", "AL30D", "GD30D", "GD30"]


def test_fees_can_kill_opportunity():
    a = q("AL30", 1390, 1400, 1.0, 1.01)
    b = q("GD30", 1405, 1410, 1.0, 1.0)       # ~0.36% bruto
    assert find_opportunities([a, b], fee_pct=0.0, min_profit_pct=0.3)
    assert not find_opportunities([a, b], fee_pct=0.15, min_profit_pct=0.3)


def test_max_nominals_is_min_of_four_legs():
    a = Quote("AL30", 1390, 1400, 1.0, 1.01, 0, 500, 300, 0)
    b = Quote("GD30", 1450, 1460, 0.98, 0.99, 200, 0, 0, 900)
    o = find_opportunities([a, b], 0, 0.3)[0]
    assert o["max_nominals"] == min(500, 300, 900, 200)


def test_invalid_quotes_ignored():
    a = q("AL30", 0, 1400, 1.0, 1.01)
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    assert find_opportunities([a, b], 0, 0.3) == []
