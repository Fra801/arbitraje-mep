import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arbitrage import Quote, find_opportunities, mep_table, plan_trade  # noqa: E402


def q(sym, bid_ars, ask_ars, bid_usd, ask_usd, qty=100000):
    return Quote(sym, bid_ars, ask_ars, bid_usd, ask_usd, qty, qty, qty, qty)


def opp_between(a, b, fee=0.0):
    return find_opportunities([a, b], fee_pct=fee, min_profit_pct=0.3)[0]


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


def test_invalid_quotes_ignored():
    a = q("AL30", 0, 1400, 1.0, 1.01)
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    assert find_opportunities([a, b], 0, 0.3) == []


def test_opportunity_without_volume_is_discarded():
    a = Quote("AL30", 1390, 1400, 1.0, 1.01, 0, 500, 0, 0)   # sin volumen en USD
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    assert find_opportunities([a, b], 0, 0.3) == []


def test_mep_medio_in_table():
    t = mep_table([q("AL30", 1390, 1400, 1.0, 1.01)])[0]
    assert t["mep_medio"] == round((t["mep_compra"] + t["mep_venta"]) / 2, 2)


def test_plan_uses_price_per_100_nominals():
    # Precios reales de AL30 (cada 100 nominales): ask $83.690 -> ~$837 por nominal.
    # Con $200.000 se compran ~239 nominales, no 100.000.
    a = q("AL30", 83580, 83690, 53.40, 53.42)
    b = q("GD30", 90000, 90100, 57.0, 57.1)   # MEP venta mucho mayor, solo para forzar la oportunidad
    o = opp_between(a, b)
    p = plan_trade(o, 200_000)
    assert p["nominals_a"] == 238          # floor(200000 * 100 / 83690)
    assert p["cost_ars"] <= 200_000
    assert abs(p["cost_ars"] - p["nominals_a"] * 83690 / 100) < 0.01


def test_second_bond_uses_dollars_from_first_not_same_nominals():
    a = q("AL30", 1390, 1400, 1.0, 1.01)
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    o = opp_between(a, b)
    p = plan_trade(o, 1_000_000)
    n_a, n_b = p["nominals_a"], p["nominals_b"]
    usd_in = n_a * 1.0 / 100
    usd_out = n_b * 0.99 / 100
    assert usd_out <= usd_in + 1e-9         # nunca se gastan más dólares de los que entran
    assert n_b != n_a                       # distintas cantidades porque los precios difieren


def test_plan_limited_by_market_volume():
    a = Quote("AL30", 1390, 1400, 1.0, 1.01, 1000, 50, 80, 1000)   # cap_a = 50
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    o = opp_between(a, b)
    p = plan_trade(o, 10_000_000)
    assert p["nominals_a"] <= 50


def test_plan_none_when_capital_too_small():
    a = q("AL30", 1390, 1400, 1.0, 1.01)
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    o = opp_between(a, b)
    assert plan_trade(o, 1) is None


def test_plan_profit_is_positive_and_after_fees():
    a = q("AL30", 1390, 1400, 1.0, 1.01)
    b = q("GD30", 1450, 1460, 0.98, 0.99)
    o = opp_between(a, b, fee=0.15)
    p = plan_trade(o, 1_000_000)
    assert p["profit_ars"] > 0
    assert p["fees_ars"] > 0
