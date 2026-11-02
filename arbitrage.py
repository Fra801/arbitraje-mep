"""Motor de arbitraje de dólar MEP implícito entre bonos.

Para cada bono hay dos especies: en pesos (AL30) y en dólares (AL30D).
Con las puntas de ambas se calcula:

  mep_compra = ask_pesos / bid_usd   -> pesos que pagás por cada USD obtenido
                                         (comprás en pesos, vendés en USD)
  mep_venta  = bid_pesos / ask_usd   -> pesos que recibís por cada USD entregado
                                         (comprás en USD, vendés en pesos)
  mep_medio  = promedio de ambos

Hay desarbitraje cuando existe un bono A y un bono B tales que
mep_venta(B) > mep_compra(A) (descontando comisiones): pesos -> USD por A,
USD -> pesos por B, y terminás con más pesos de los que empezaste.

IMPORTANTE: IOL cotiza los bonos por cada 100 nominales (UNIT), mientras que las
cantidades de las órdenes y de las puntas se expresan en nominales.
"""
import math
from dataclasses import dataclass, asdict

UNIT = 100  # los precios de los bonos son por cada 100 nominales


@dataclass
class Quote:
    symbol: str          # ej. "AL30"
    bid_ars: float
    ask_ars: float
    bid_usd: float
    ask_usd: float
    bid_ars_qty: float = 0
    ask_ars_qty: float = 0
    bid_usd_qty: float = 0
    ask_usd_qty: float = 0

    @property
    def valid(self):
        return all(v and v > 0 for v in (self.bid_ars, self.ask_ars, self.bid_usd, self.ask_usd))

    @property
    def mep_compra(self):
        return self.ask_ars / self.bid_usd

    @property
    def mep_venta(self):
        return self.bid_ars / self.ask_usd

    @property
    def mep_medio(self):
        return (self.mep_compra + self.mep_venta) / 2


def plan_trade(opp, capital_ars=None):
    """Calcula los nominales de cada una de las 4 patas.

    capital_ars: pesos a invertir. Si es None, usa el máximo que permite el mercado.
    Devuelve None si no se puede operar (sin volumen o capital insuficiente).

    Los dólares que salen de vender A alcanzan para comprar una cantidad distinta de B
    (tienen precios distintos), por eso las patas 3 y 4 usan nominales propios.
    """
    ask_a, bid_usd_a = opp["ask_ars_a"], opp["bid_usd_a"]
    ask_usd_b, bid_b = opp["ask_usd_b"], opp["bid_ars_b"]
    cap_a, cap_b = int(opp["cap_a"]), int(opp["cap_b"])
    if cap_a <= 0 or cap_b <= 0:
        return None

    n_a = cap_a if capital_ars is None else min(cap_a, math.floor(capital_ars * UNIT / ask_a))
    if n_a < 1:
        return None
    n_b = min(cap_b, math.floor(n_a * bid_usd_a / ask_usd_b))
    if n_b < 1:
        return None
    # si el volumen de B es el límite, comprar solo los A necesarios
    n_a = min(n_a, math.ceil(n_b * ask_usd_b / bid_usd_a - 1e-9))

    cost_ars = n_a * ask_a / UNIT
    usd_in = n_a * bid_usd_a / UNIT
    usd_out = n_b * ask_usd_b / UNIT
    proceeds_ars = n_b * bid_b / UNIT
    mep_ref = ask_a / bid_usd_a
    mep_venta_b = bid_b / ask_usd_b
    fees = opp.get("fee_pct", 0.0) / 100 * (cost_ars + proceeds_ars + (usd_in + usd_out) * mep_ref)
    usd_left = max(usd_in - usd_out, 0.0)
    profit = proceeds_ars + usd_left * mep_venta_b - cost_ars - fees

    return {
        "via_usd": opp["via_usd"], "back_to_ars": opp["back_to_ars"],
        "nominals_a": n_a, "nominals_b": n_b,
        "cost_ars": round(cost_ars, 2),
        "proceeds_ars": round(proceeds_ars, 2),
        "usd_left": round(usd_left, 2),
        "fees_ars": round(fees, 2),
        "profit_ars": round(profit, 2),
        "profit_pct": round(profit / cost_ars * 100, 3) if cost_ars else 0,
        "legs": [
            {"side": "buy", "symbol": opp["via_usd"], "price": ask_a, "quantity": n_a},
            {"side": "sell", "symbol": opp["via_usd"] + "D", "price": bid_usd_a, "quantity": n_a},
            {"side": "buy", "symbol": opp["back_to_ars"] + "D", "price": ask_usd_b, "quantity": n_b},
            {"side": "sell", "symbol": opp["back_to_ars"], "price": bid_b, "quantity": n_b},
        ],
    }


def find_opportunities(quotes, fee_pct=0.0, min_profit_pct=0.3):
    """Devuelve oportunidades ordenadas por ganancia estimada (desc).

    fee_pct: comisión por operación en % (cada ida/vuelta tiene 4 patas).
    min_profit_pct: ganancia neta mínima en % para alertar.
    """
    qs = [q for q in quotes if q.valid]
    out = []
    for a in qs:          # bono por el que conseguís USD
        for b in qs:      # bono por el que volvés a pesos
            if a.symbol == b.symbol:
                continue
            gross = (b.mep_venta / a.mep_compra - 1) * 100
            net = gross - 4 * fee_pct
            if net >= min_profit_pct:
                opp = {
                    "via_usd": a.symbol,
                    "back_to_ars": b.symbol,
                    "mep_compra": round(a.mep_compra, 2),
                    "mep_venta": round(b.mep_venta, 2),
                    "gross_pct": round(gross, 3),
                    "net_pct": round(net, 3),
                    "fee_pct": fee_pct,
                    # puntas (precios por 100 nominales) y volumen en nominales
                    "ask_ars_a": a.ask_ars, "bid_usd_a": a.bid_usd,
                    "ask_usd_b": b.ask_usd, "bid_ars_b": b.bid_ars,
                    "cap_a": min(a.ask_ars_qty or 0, a.bid_usd_qty or 0),
                    "cap_b": min(b.ask_usd_qty or 0, b.bid_ars_qty or 0),
                }
                full = plan_trade(opp)
                if not full:
                    continue  # sin volumen real para operarla
                opp["max_capital_ars"] = full["cost_ars"]
                opp["legs"] = full["legs"]
                out.append(opp)
    out.sort(key=lambda o: o["net_pct"], reverse=True)
    return out


def mep_table(quotes):
    return [
        {"symbol": q.symbol, "mep_compra": round(q.mep_compra, 2),
         "mep_venta": round(q.mep_venta, 2), "mep_medio": round(q.mep_medio, 2),
         **{k: v for k, v in asdict(q).items() if k != "symbol"}}
        for q in quotes if q.valid
    ]
