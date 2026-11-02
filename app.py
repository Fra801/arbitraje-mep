import os
import secrets
import threading
import time

from flask import Flask, jsonify, render_template, request, session

from arbitrage import Quote, find_opportunities, mep_table, plan_trade
from iol import IOLClient, IOLError

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Si es "1" (por defecto) NO se envían órdenes reales: solo se simulan.
DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "5"))
DEFAULT_SYMBOLS = os.environ.get("SYMBOLS", "AL30,GD30,AL35,GD35,AE38,GD38,AL41,GD41").split(",")

SESSIONS = {}  # sid -> dict(client, state, symbols, fee, min_profit, plazo, lock)


def _poll_loop(sid):
    s = SESSIONS.get(sid)
    while s and not s["stop"].is_set():
        try:
            quotes = []
            for sym in s["symbols"]:
                ars = s["client"].quote(sym, s["plazo"])
                usd = s["client"].quote(sym + "D", s["plazo"])
                if not ars or not usd:
                    continue
                quotes.append(Quote(sym, ars[0], ars[2], usd[0], usd[2],
                                    ars[1], ars[3], usd[1], usd[3]))
            opps = find_opportunities(quotes, s["fee"], s["min_profit"])
            s["state"] = {"ts": time.time(), "table": mep_table(quotes),
                          "opportunities": opps, "error": None}
        except Exception as e:  # noqa: BLE001
            s["state"]["error"] = str(e)
        s["stop"].wait(POLL_SECONDS)


def _current():
    sid = session.get("sid")
    return SESSIONS.get(sid) if sid else None


@app.get("/")
def index():
    return render_template("index.html", dry_run=DRY_RUN, symbols=",".join(DEFAULT_SYMBOLS))


@app.post("/api/login")
def login():
    j = request.get_json(force=True)
    try:
        client = IOLClient(j.get("username", ""), j.get("password", ""))
    except IOLError as e:
        return jsonify(error=str(e)), 401
    except Exception:  # noqa: BLE001
        return jsonify(error="No se pudo conectar con IOL"), 502
    old = _current()
    if old:
        old["stop"].set()
    sid = secrets.token_hex(16)
    SESSIONS[sid] = {
        "client": client, "stop": threading.Event(),
        "state": {"ts": 0, "table": [], "opportunities": [], "error": None},
        "symbols": [x.strip().upper() for x in j.get("symbols", ",".join(DEFAULT_SYMBOLS)).split(",") if x.strip()],
        "fee": float(j.get("fee", 0.15)), "min_profit": float(j.get("min_profit", 0.3)),
        "plazo": j.get("plazo", "t1"),
    }
    session["sid"] = sid
    threading.Thread(target=_poll_loop, args=(sid,), daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    s = _current()
    if s:
        s["stop"].set()
        SESSIONS.pop(session.pop("sid"), None)
    return jsonify(ok=True)


@app.get("/api/state")
def state():
    s = _current()
    if not s:
        return jsonify(error="no_session"), 401
    return jsonify(s["state"])


def _plan_from_request(s):
    """Devuelve (plan, error_response) a partir de la oportunidad y el capital pedidos."""
    j = request.get_json(force=True)
    try:
        capital = float(j.get("capital", 0))
    except (TypeError, ValueError):
        capital = 0
    if capital <= 0:
        return None, (jsonify(error="Indicá cuántos pesos querés invertir"), 400)
    opp = next((o for o in s["state"]["opportunities"]
                if o["via_usd"] == j.get("via_usd") and o["back_to_ars"] == j.get("back_to_ars")), None)
    if not opp:
        return None, (jsonify(error="La oportunidad ya no está vigente"), 409)
    plan = plan_trade(opp, capital)
    if not plan:
        return None, (jsonify(error="Capital insuficiente o sin volumen en el mercado"), 400)
    plan["capital_requested"] = capital
    plan["capped"] = plan["cost_ars"] < capital * 0.98  # el mercado no alcanza para todo el capital
    return plan, None


@app.post("/api/plan")
def plan():
    """Calcula (sin operar) qué se compraría y vendería con el capital indicado."""
    s = _current()
    if not s:
        return jsonify(error="no_session"), 401
    p, err = _plan_from_request(s)
    return err if err else jsonify(p)


@app.post("/api/execute")
def execute():
    s = _current()
    if not s:
        return jsonify(error="no_session"), 401
    p, err = _plan_from_request(s)
    if err:
        return err
    results = []
    try:
        for leg in p["legs"]:
            if DRY_RUN:
                results.append({**leg, "simulated": True})
            else:
                r = s["client"].place_order(leg["side"], leg["symbol"], leg["quantity"],
                                            leg["price"], s["plazo"])
                results.append({**leg, "response": r})
    except IOLError as e:
        return jsonify(error=str(e), done=results), 502
    return jsonify(ok=True, dry_run=DRY_RUN, legs=results, plan=p)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
