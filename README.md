# Arbitraje dólar MEP (bonos AL/GD) con InvertirOnline

Panel web local que monitorea cada pocos segundos el dólar MEP implícito de varios bonos
(precio en pesos ÷ precio en dólares) y **suena una alerta** cuando aparece un desarbitraje.
Desde el panel podés ejecutar la operación (4 órdenes límite) con un clic y confirmación.

## Cómo funciona

Para cada bono (ej. `AL30` y `AL30D`) se calcula con las puntas:

- `MEP compra = ask_pesos / bid_usd` (comprás en pesos, vendés en USD)
- `MEP venta  = bid_pesos / ask_usd` (comprás en USD, vendés en pesos)

Hay oportunidad cuando `MEP venta(B) > MEP compra(A)` descontadas las comisiones:
comprás A en pesos, lo vendés en dólares, comprás B en dólares y lo vendés en pesos.

En el panel cada bono muestra el MEP de compra, el de venta y el promedio.

**Cuánto invertir:** en cada oportunidad escribís los *pesos* a invertir. La app calcula los
nominales de cada una de las 4 órdenes (IOL cotiza los bonos cada 100 nominales), los limita al
volumen disponible en el mercado y te muestra el detalle y la ganancia estimada antes de pedirte
confirmación. Los nominales de la 3.ª y 4.ª orden se calculan con los dólares que realmente salen
de la 2.ª, porque los dos bonos tienen precios distintos.

## Uso

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abrí http://127.0.0.1:5000, ingresá tu usuario y contraseña de IOL y dejá la pestaña abierta
(el navegador necesita la pestaña abierta para reproducir el sonido).

## Configuración (variables de entorno)

| Variable | Default | Descripción |
|---|---|---|
| `DRY_RUN` | `1` | `1` simula las órdenes; poné `0` para enviarlas realmente |
| `POLL_SECONDS` | `5` | Frecuencia de consulta a IOL |
| `SYMBOLS` | `AL30,GD30,AL35,GD35,AE38,GD38,AL41,GD41` | Bonos a monitorear (sin la `D`) |
| `SECRET_KEY` | aleatoria | Clave de sesión de Flask |

## Seguridad

- Las credenciales **no se guardan en disco**: se usan para obtener el token de IOL y viven solo en memoria.
- La app escucha solo en `127.0.0.1`. No la expongas a internet sin HTTPS y autenticación propia.
- Empezá siempre con `DRY_RUN=1`.

## Riesgos a tener en cuenta

- Las 4 órdenes **no son atómicas**: puede ejecutarse una pata y otra no, o el precio puede moverse. Las órdenes son límite al precio de la punta.
- Las puntas pueden tener poco volumen: la app limita los nominales al mínimo de las 4 patas.
- Comisiones, derechos de mercado y plazo de liquidación (CI/24hs) afectan el resultado real.
- Revisá los términos de uso de la API de IOL y sus límites de consultas.
- Esto no es asesoramiento financiero.

## Tests

```bash
pytest
```
