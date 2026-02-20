# Fase 1 – Completada. Cómo probar

## Checklist Fase 1

- [x] **Config**: `contract_type` (rise_fall | multiplier), parámetros multiplier (duration, TP/SL %)
- [x] **TP/SL**: Cálculo en USD desde stake y porcentajes de config
- [x] **OrderExecutor**: `execute_multiplier()` con limit_order (take_profit, stop_loss)
- [x] **Engine**: TradeIntent con TP/SL; usa tipo efectivo (YAML + runtime) para elegir multiplier vs rise_fall
- [x] **DB**: Columnas `take_profit` y `stop_loss` en `trades`
- [x] **API**: `/health` con `contract_type` efectivo; **GET/POST `/config`** para ver y cambiar tipo de contrato
- [x] **Frontend**: Muestra mercado, tipo de contrato, TP/SL en última operación; **selector para Rise/Fall vs Multiplicador** y botón Guardar

## Cómo saber en qué mercado operas

- **Mercado (símbolo)**: En el dashboard, sección "Configuración de operación" → "Mercado actual". El valor viene de `config/default.yaml` → `trading.symbol` (ej. R_75).
- **Cambiar mercado**: Edita `config/default.yaml`, cambia `trading.symbol` (ej. a `R_50` o `R_100`), guarda y **reinicia el motor** (engine).

## Cómo operar en Multiplicadores

1. **Desde el frontend** (recomendado): En "Configuración de operación" → "Tipo de contrato" elige **Multiplicador** y pulsa **Guardar**. El cambio aplica en la **siguiente** operación (no hace falta reiniciar).
2. **Desde config**: En `config/default.yaml` pon `trading.contract_type: "multiplier"` y, si quieres, ajusta `trading.multiplier` (duration, take_profit_percent_of_stake, stop_loss_percent_of_stake). Reinicia el motor.

Con **Multiplicador** el bot usa TP/SL en USD según los porcentajes de la config (p. ej. 50% del stake como beneficio objetivo y 50% como pérdida máxima por operación).

## Pasos para probar que todo funciona

1. **Arrancar backend API**:  
   `cd backend` → `.\\.venv\\Scripts\\python.exe -m src.app.main api`
2. **Arrancar motor**: En otra terminal, `cd backend` → `.\\.venv\\Scripts\\python.exe -m src.app.main engine`
3. **Arrancar frontend**: `cd frontend/frontend` → `npm run dev`
4. Abre el dashboard y comprueba:
   - "Mercado actual" muestra el símbolo configurado (ej. Volatility 75 Index (R_75)).
   - "Tipo de contrato" muestra Rise/Fall 1m o Multiplicador según config / runtime.
5. Cambia a **Multiplicador** en el selector y pulsa **Guardar**. Recarga la página o espera al siguiente polling: debe seguir mostrando "Multiplicador".
6. Cuando el motor abra una operación en modo multiplier, en la tabla de trades y en el resumen deberían verse columnas **TP** y **SL** en USD para esa operación.

## Resumen

- **Mercado**: Solo desde `config/default.yaml` → `trading.symbol` + reinicio.
- **Rise/Fall vs Multiplicador**: Desde el **dashboard** (selector + Guardar) o desde YAML; con el dashboard no hace falta reiniciar.
