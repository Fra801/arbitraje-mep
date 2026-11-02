"""Motor de arbitraje de dólar MEP implícito entre bonos.

Para cada bono hay dos especies: en pesos (AL30) y en dólares (AL30D).
Con las puntas de ambas se calcula:

  mep_compra = ask_pesos / bid_usd   -> pesos que pagás por cada USD obtenido
                                         (comprás en pesos, vendés en USD)
  mep_venta  = bid_pesos / ask_usd   -> pesos que recibís por cada USD entregado
                                         (comprás en USD, vendés en pesos)

Hay desarbitraje cuando existe un bono A y un bono B tales que
mep_venta(B) > mep_compra(A) (descontando comisiones): pesos -> USD por A,
USD -> pesos por B, y terminás con más pesos de los que empezaste.
"""
from dataclasses import dataclass, asdict


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
                # nominales máximos que soportan las puntas (las 4 patas)
                max_nominals = min(
                    a.ask_ars_qty or 0, a.bid_usd_qty or 0,
                    b.ask_usd_qty or 0, b.bid_ars_qty or 0,
                )
                out.append({
                    "via_usd": a.symbol,
                    "back_to_ars": b.symbol,
                    "mep_compra": round(a.mep_compra, 2),
                    "mep_venta": round(b.mep_venta, 2),
                    "gross_pct": round(gross, 3),
                    "net_pct": round(net, 3),
                    "max_nominals": max_nominals,
                    "legs": [
                        {"side": "buy", "symbol": a.symbol, "price": a.ask_ars},
                        {"side": "sell", "symbol": a.symbol + "D", "price": a.bid_usd},
                        {"side": "buy", "symbol": b.symbol + "D", "price": b.ask_usd},
                        {"side": "sell", "symbol": b.symbol, "price": b.bid_ars},
                    ],
                })
    out.sort(key=lambda o: o["net_pct"], reverse=True)
    return out


def mep_table(quotes):
    return [
        {"symbol": q.symbol, "mep_compra": round(q.mep_compra, 2),
         "mep_venta": round(q.mep_venta, 2), **{k: v for k, v in asdict(q).items() if k != "symbol"}}
        for q in quotes if q.valid
    ]
