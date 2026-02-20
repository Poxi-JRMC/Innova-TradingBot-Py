# Guía en texto: estado del bot, por qué no ves operaciones/indicadores, y con qué mejorar

## 1. ¿Se modificó algo que rompa la estrategia o las métricas?

**No.** La estrategia (Trend Pullback), los indicadores (EMA, RSI, ATR), el filtro HTF, el filtro de calidad y el cálculo de métricas siguen igual. Nada de eso se tocó para que “dejen de funcionar”. Lo que puede pasar es que **no veas datos en el frontend** por cómo están conectados el motor y la API.

---

## 2. Cómo está conectado todo (motor ↔ API ↔ frontend)

- **Motor (engine):** se ejecuta con `python -m src.app.main engine`. Es un proceso aparte. Ese proceso:
  - Conecta a Deriv, recibe ticks, construye velas 1m, calcula indicadores y la estrategia.
  - Cada **5 segundos** escribe las métricas en dos sitios:
    1. En la base de datos SQLite (`data/trading_bot.db`), en la tabla `events`, con `type = 'metrics'` y en `data_json` los valores (balance, ema_fast, ema_slow, atr, rsi, candles_closed, symbol, connected, etc.).
    2. En el archivo `data/metrics.json` (mismo contenido).

- **API:** se ejecuta con `python -m src.app.main api`. Es **otro proceso**. No comparte memoria con el motor. Para mostrar métricas:
  - Primero intenta leer la **última fila** de `events` donde `type = 'metrics'`.
  - Si no hay ninguna (o está vacía), ahora también intenta leer **data/metrics.json** como respaldo.

- **Frontend:** llama a `GET /metrics`. La API devuelve algo como `{ "ok": true, "metrics": { "ts": "...", "data": { "balance": ..., "ema_fast": ..., "ema_slow": ..., "atr": ..., "rsi": ..., ... } } }`. El frontend usa solo `metrics.data` para la pestaña Métricas y para “Indicadores técnicos” (EMA rápida, EMA lenta, ATR, RSI).

Por tanto:
- Si **solo ejecutas la API** y no el motor, no hay nadie escribiendo métricas → en el frontend verás “-” en indicadores y puede que poco o nada en Métricas.
- Si **ejecutas el motor y la API** desde la **misma carpeta del proyecto** (mismo `data/` y misma `data/trading_bot.db`), la API debería mostrar métricas (desde la BD o, si no hay eventos, desde `data/metrics.json`).
- Los **indicadores** (EMA, RSI, ATR) solo tienen valor **después del calentamiento** del motor (suficientes velas 1m para EMA lenta, RSI, ATR). Hasta entonces, en el frontend pueden aparecer como “-”.

---

## 3. Por qué no ves operaciones (trades) en el frontend

Las operaciones solo existen si:

1. El **motor está corriendo** (para generar señales).
2. **dry_run está en false** (en config o con `DEVELOPMENT__DRY_RUN=0` en `.env`), para que realmente compre/venda en Deriv.
3. La señal pasa **todos los filtros**: tendencia de marco superior (HTF), filtro de calidad (score mínimo, RSI dentro de banda), kill-switch desactivado, y el risk firewall (drawdown, pérdida diaria, rachas, etc.).
4. El **position sizer** devuelve un stake > 0 (score no demasiado bajo).

Si algo de eso no se cumple, no se abre operación y es normal no ver trades en el frontend. No es un fallo de “métricas modificadas”; es que el flujo está pensado para ser selectivo.

---

## 4. Por qué “antes” veías algo en Indicadores técnicos y “ahora” no

Posibles causas (sin haber cambiado la lógica de la estrategia ni de las métricas):

- **Motor no estaba corriendo cuando miraste:** si solo tenías la API y el frontend abiertos, no hay proceso que escriba métricas → indicadores en “-”.
- **Motor recién arrancado:** hasta que no pasan suficientes velas 1m (por ejemplo ~50 para EMA lenta), los indicadores pueden ser `null` y el frontend muestra “-”.
- **API y motor con distinta carpeta de trabajo:** si el motor escribe en `data/` de una ruta y la API lee la BD o el archivo de otra, la API no ve las métricas nuevas. Conviene ejecutar ambos desde la misma raíz del proyecto (por ejemplo `botTrading/backend`).
- **Base de datos vacía o sin eventos `metrics`:** por defecto la API ahora también usa `data/metrics.json` si no hay eventos en la BD, así que deberías ver algo siempre que el motor esté escribiendo en esa carpeta.

---

## 5. Qué hacer para ver indicadores y comprobar que todo va bien

1. **Arrancar el motor** en una terminal (desde la carpeta del backend):
   ```bash
   cd botTrading\backend
   .\.venv\Scripts\python.exe -m src.app.main engine
   ```
2. **Arrancar la API** en otra terminal (misma carpeta):
   ```bash
   .\.venv\Scripts\python.exe -m src.app.main api
   ```
3. Abrir el frontend y entrar en **Métricas**. Esperar 1–2 minutos (al menos un ciclo de 5 s de escritura de métricas y, si aplica, calentamiento de indicadores). Deberías ver:
   - Velas cerradas (1 min) subiendo.
   - Luego EMA rápida, EMA lenta, ATR, RSI (si el motor está en multi-mercado, pueden ser del último símbolo que actualizó).
4. En **Eventos** deberías ver eventos `engine` al arrancar y, cada 5 s, eventos `metrics`. Si hay señales omitidas por dry_run, verás `dry_run_skip`.

Con eso confirmas que la estrategia y las métricas están funcionando y que el problema era de conexión motor ↔ API o de no tener el motor en marcha.

---

## 6. Con qué estamos empezando para mejorar y ver rentabilidad

Punto de partida recomendado:

1. **Dejar claro que motor y API están conectados:** ya está el fallback de métricas desde `data/metrics.json` para que la pestaña Métricas e Indicadores técnicos tengan datos aunque no haya eventos en la BD.
2. **Comprobar en vivo:** con motor + API + frontend, ver que los indicadores se rellenan tras el calentamiento y que en Eventos aparecen `engine` y `metrics` (y `dry_run_skip` si aplica).
3. **Para ver operaciones reales:** poner `dry_run: false` (o `DEVELOPMENT__DRY_RUN=0`), desactivar kill-switch y asegurarte de que los parámetros (min_score, RSI, HTF, etc.) no sean tan estrictos que nunca pasen señales. Puedes aflojar un poco en config para ver trades de prueba.
4. **Siguientes mejoras útiles para rentabilidad:** las que ya están en el README: trailing stop / TP-SL por ATR, filtro por sesión, backtest con métricas (Sharpe, drawdown), alertas y dashboard de PnL. Todo eso se puede ir añadiendo sin tocar la lógica actual de estrategia ni el cálculo de métricas.

Resumen: la estrategia y las métricas no se han modificado para que dejen de funcionar. Lo que puede fallar es tener el motor parado, no tener calentamiento aún, o motor y API usando carpetas distintas. Con motor y API corriendo desde el mismo backend y el fallback de `data/metrics.json`, deberías volver a ver Indicadores técnicos y, cuando se den las condiciones, operaciones en el frontend.
