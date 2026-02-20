# Deriv Trading Bot (Índices Sintéticos) – MVP profesional

Backend en Python (asyncio + websockets) y API en FastAPI.

## Requisitos

- Python 3.11+ (recomendado). *Nota: el repo puede correr en 3.13, pero el target es 3.11+.*

## 1) Configuración Deriv (DEMO)

Sigue: `docs/deriv_tokens.md`

Luego edita `config/default.yaml` y completa:

```yaml
deriv:
  app_id: "..."
  api_token: "..."
```

## 2) Ejecutar Engine

```bash
python -m src.app.main engine
```

Por defecto el motor corre en **dry_run** (no abre operaciones en Deriv). Para que ejecute de verdad:

- En `config/default.yaml`: pon `development.dry_run: false`, **o**
- En `.env`: añade `DEVELOPMENT__DRY_RUN=0`

**Dónde revisar dry_run y “fallos”:**
- **Eventos (GET /events o pestaña Eventos en la UI):** al arrancar verás un evento `engine` con `data.dry_run`. Si una señal se omite por dry_run, ahora verás un evento **`dry_run_skip`** (“Operación no ejecutada (dry_run activo)”). Los **`trade_error`** solo aparecen cuando dry_run está en false y falla la ejecución en Deriv (proposal/buy).
- **Consola del motor:** al omitir por dry_run se imprime `dry_run_skip_execution` con symbol, side, stake.

**Checklist para ver tu primera operación:**
1. **Token Deriv** en `config/default.yaml` (o `.env`) y motor + API corriendo desde la misma carpeta del backend.
2. **dry_run en false:** `development.dry_run: false` en config o `DEVELOPMENT__DRY_RUN=0` en `.env`; reinicia el motor.
3. **Kill-switch desactivado:** en la UI (Inicio) o `POST /killswitch` con `"enabled": false`.
4. **Esperar señales:** la estrategia solo abre cuando hay tendencia + RSI en zona de pullback (puede tardar varios minutos). En la pestaña **Eventos** verás `trade_open` cuando se abra una; si ves `dry_run_skip` seguido de muchos `metrics`, las señales se están generando pero estaban en simulación.
5. Si quieres más señales de prueba (menos estricto): en config puedes subir un poco `quality_filter.rsi_call_max` (ej. 70) y bajar `rsi_put_min` (ej. 33), o dejar `min_score` en 0.

Entonces el bot:
- conecta a Deriv WS, autoriza, muestra balance
- se suscribe a ticks (o a R_50, R_75, R_100 en multi-mercado)
- construye velas 1m, genera señales y **abre contratos** (Rise/Fall o Multiplier según `trading.contract_type`)

## 3) Ejecutar API

```bash
python -m src api
```

Endpoints:
- `GET /status`
- `GET /metrics`
- `GET /trades`
- `GET /config`
- `GET /killswitch`
- `POST /killswitch`

## Kill-switch

Persistente en `data/killswitch.json`.

### Activar

```bash
curl -X POST http://localhost:8000/killswitch \
  -H "Content-Type: application/json" \
  -d "{\"enabled\": true, \"reason\": \"manual_stop\"}"
```

### Desactivar

```bash
curl -X POST http://localhost:8000/killswitch \
  -H "Content-Type: application/json" \
  -d "{\"enabled\": false, \"reason\": \"reset\"}"
```

## Estado actual / ¿Está funcional?

Sí. Con la estrategia unificada (Trend Pullback + soportes y resistencias), filtros (HTF, calidad, S/R, kill-switch), risk (position sizer, firewall) y ejecución (Rise/Fall y Multiplier) ya implementados, el bot es **funcional de punta a punta**:

1. **Engine** → ticks → velas 1m → indicadores (EMA, RSI, ATR) → señal + score.
2. **Filtros** → tendencia de marco superior (5m), calidad (min_score, RSI), **soportes/resistencias** (CALL solo cerca de soporte, PUT solo cerca de resistencia), kill-switch.
3. **Risk** → position sizing por score, firewall (drawdown, pérdida diaria, rachas).
4. **Ejecución** → dry_run (simular) o real en Deriv (Rise/Fall 1m o Multiplier con TP/SL).

Requisitos para que opere de verdad: token Deriv en config, `development.dry_run: false` (o `DEVELOPMENT__DRY_RUN=0` en `.env`) y kill-switch desactivado.

---

## Posibles mejoras (general)

- **Estrategia / señales**
  - Añadir más patrones de price action (ej. rechazos en niveles, rupturas de rango).
  - Estrategias alternativas seleccionables por config (ej. breakout, mean reversion).
  - Filtro por sesión (Londres, NY, Asia) o por volatilidad horaria.

- **Riesgo y ejecución**
  - Trailing stop o TP/SL dinámicos según ATR.
  - Límite de exposición simultánea (máx. N contratos abiertos o riesgo total).
  - Reintentos con backoff en fallos de red/API de Deriv.

- **Datos y backtest**
  - Persistir velas/historial en DB para no depender solo de Deriv en vivo.
  - Backtest con comisiones y deslizamiento; métricas (Sharpe, max drawdown).
  - Export de trades (CSV/JSON) para análisis externo.

- **Operación y observabilidad**
  - El WebSocket a Deriv ya reconecta solo (exponential backoff). El motor detecta caída y vuelta: en **Métricas** verás "Motor conectado: No" si se cayó y "Sí" al reconectar; en **Eventos** aparecen `ws_disconnected` y `ws_reconnected`.
  - Alertas (Telegram/email) en trade_error, kill-switch o drawdown alto.
  - Dashboard con PnL en tiempo real, win rate y estado del motor.

- **Infra y código**
  - Tests unitarios e integración (estrategia, sizer, executor mock).
  - Opción de PostgreSQL para eventos/trades en producción.
  - Documentar variables de entorno y ejemplos de `config` para distintos entornos.

---

## Estructura

Backend (Python):
- `src/api/` Deriv WS client + FastAPI
- `src/market/` ticks→velas→indicadores
- `src/risk/` RiskFirewall + Kill-switch
- `src/storage/` SQLite repo (events + trades)
- `src/engine.py` loop principal (MVP)

Frontend (próximo):
- `frontend/` (esqueleto listo para Vite/React/TS)

