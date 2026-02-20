# Cómo arrancar y probar el bot (R_75)

Sigue estos pasos para poder operar solo el índice R_75 y comprobar que todo funciona.

---

## 1. Entra en la carpeta del backend

En PowerShell:

```powershell
cd "c:\Users\POXIFLOW\Documents\TRABAJOS\bot de trading\botTrading\backend"
```

**Importante:** Todos los comandos siguientes se ejecutan desde esta carpeta. El bot busca `config/default.yaml` y la carpeta `data/` aquí.

---

## 2. Crea el entorno virtual e instala dependencias (solo la primera vez)

**Crear el venv** (si no existe la carpeta `.venv`):

```powershell
python -m venv .venv
```

**Activar el venv** (en PowerShell usa `&` delante para que reconozca el script):

```powershell
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell no ejecuta scripts (error de "política de ejecución"), usa el Python del venv **sin activar**:

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Luego para arrancar el engine siempre puedes usar:

```powershell
.\.venv\Scripts\python.exe -m src.app.main engine
```

---

## 3. Comprueba la configuración

- **Token Deriv:** El archivo `.env` en `backend` debe tener tu token de cuenta **DEMO** (no real):
  - `DERIV__APP_ID=1089` (o el que uses)
  - `DERIV__API_TOKEN=tu_token_demo`

- **Símbolo:** En `config/default.yaml` ya está `trading.symbol: "R_75"`. No hace falta cambiarlo para estas pruebas.

- **Kill switch:** Si quieres que el bot **no abra operaciones** al inicio, activa el kill switch desde la API (paso 5) antes de arrancar el engine, o deja `kill_switch.enabled: true` en el YAML. Para que **sí opere**, déjalo en `false` y no lo actives por API.

---

## 4. Arrancar el motor de trading (engine)

En una terminal, desde `backend`:

**Si activaste el venv:**
```powershell
python -m src.app.main engine
```

**Si no activaste (o te da error):**
```powershell
.\.venv\Scripts\python.exe -m src.app.main engine
```

Deberías ver algo como:

- Conexión al WebSocket de Deriv
- Mensaje de autorización
- Balance de la cuenta DEMO
- Suscripción a ticks de **R_75**
- Cada minuto, cierre de vela e indicadores (EMA, ATR, RSI)
- Si hay señal, el bot encolará y ejecutará un trade Rise/Fall (CALL o PUT) de 1 minuto

**Para detener:** `Ctrl+C` en esa terminal.

---

## 5. (Opcional) Arrancar la API para ver métricas y trades

En **otra** terminal, también desde `backend`:

```powershell
cd "c:\Users\POXIFLOW\Documents\TRABAJOS\bot de trading\botTrading\backend"
& .\.venv\Scripts\Activate.ps1
python -m src.app.main api
```

O sin activar: `.\.venv\Scripts\python.exe -m src.app.main api`

La API quedará en `http://localhost:8000`. Puedes usar:

- **Estado:** http://localhost:8000/health  
- **Métricas:** http://localhost:8000/metrics  
- **Trades:** http://localhost:8000/trades  
- **Kill switch:**  
  - Ver: GET http://localhost:8000/killswitch  
  - Activar (no operar): `POST http://localhost:8000/killswitch/enable` con body `{"reason": "pruebas"}`  
  - Desactivar: `POST http://localhost:8000/killswitch/disable`  

Mientras el **engine** esté corriendo, las métricas se actualizan en la API leyendo de la base de datos y de `data/metrics.json`.

---

## 6. Resumen rápido para “solo probar R_75”

| Paso | Comando / Acción |
|------|-------------------|
| 1 | `cd botTrading\backend` |
| 2 | Activar venv y `pip install -r requirements.txt` |
| 3 | Revisar `.env` (token DEMO) y `config/default.yaml` (símbolo R_75) |
| 4 | `python -m src.app.main engine` → empieza a operar R_75 en DEMO |
| 5 (opcional) | En otra terminal: `python -m src.app.main api` → ver métricas y trades por HTTP |

Con esto ya puedes operar solo R_75 y comprobar si el bot funciona end-to-end en DEMO.
