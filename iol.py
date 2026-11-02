"""Cliente mínimo de la API de InvertirOnline (https://api.invertironline.com).

Las credenciales NUNCA se guardan en disco: solo se usan para pedir el token,
que vive en memoria mientras dure la sesión.
"""
import time
import requests

BASE = "https://api.invertironline.com"


class IOLError(Exception):
    pass


class IOLClient:
    def __init__(self, username, password):
        self._username = username
        self._password = password
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self._login()

    def _token_request(self, data):
        r = requests.post(f"{BASE}/token", data=data, timeout=15)
        if r.status_code != 200:
            raise IOLError("No se pudo autenticar en IOL (usuario/contraseña incorrectos?)")
        j = r.json()
        self.access_token = j["access_token"]
        self.refresh_token = j.get("refresh_token")
        self.expires_at = time.time() + int(j.get("expires_in", 900)) - 30

    def _login(self):
        self._token_request({"username": self._username, "password": self._password,
                             "grant_type": "password"})

    def _ensure_token(self):
        if time.time() < self.expires_at:
            return
        if self.refresh_token:
            try:
                self._token_request({"refresh_token": self.refresh_token,
                                     "grant_type": "refresh_token"})
                return
            except IOLError:
                pass
        self._login()

    def _headers(self):
        self._ensure_token()
        return {"Authorization": f"Bearer {self.access_token}"}

    def quote(self, symbol, plazo="t1", mercado="bCBA"):
        """Cotización con puntas. Devuelve (bid, bid_qty, ask, ask_qty)."""
        url = f"{BASE}/api/v2/{mercado}/Titulos/{symbol}/CotizacionDetalleMobile/{plazo}"
        r = requests.get(url, headers=self._headers(), timeout=15)
        if r.status_code != 200:
            return None
        puntas = (r.json().get("puntas") or [])
        if not puntas:
            return None
        p = puntas[0]
        return (p.get("precioCompra") or 0, p.get("cantidadCompra") or 0,
                p.get("precioVenta") or 0, p.get("cantidadVenta") or 0)

    def place_order(self, side, symbol, quantity, price, plazo="t1", mercado="bCBA"):
        endpoint = "Comprar" if side == "buy" else "Vender"
        body = {"mercado": mercado, "simbolo": symbol, "cantidad": quantity,
                "precio": price, "plazo": plazo, "validez": _end_of_day(),
                "tipoOrden": "precioLimite"}
        r = requests.post(f"{BASE}/api/v2/operar/{endpoint}", json=body,
                          headers=self._headers(), timeout=15)
        if r.status_code not in (200, 201):
            raise IOLError(f"Orden rechazada ({symbol}): {r.text[:200]}")
        return r.json()


def _end_of_day():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%dT23:59:59")
