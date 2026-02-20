# Paso a paso: arrancar Engine, API y Frontend

Necesitas **3 terminales** (PowerShell o CMD). Ejecuta en este orden.

---

## Terminal 1 – API (backend REST)

La API sirve métricas, trades y kill switch al frontend.

1. Abre la primera terminal.
2. Ve a la carpeta del backend:
   ```powershell
   cd "c:\Users\POXIFLOW\Documents\TRABAJOS\bot de trading\botTrading\backend"
   ```
3. Arranca la API (sin activar el venv puedes usar la ruta directa):
   ```powershell
   .\.venv\Scripts\python.exe -m src.app.main api
   ```
4. Debe aparecer algo como: `Uvicorn running on http://0.0.0.0:8000`
5. **Deja esta terminal abierta.** La API debe seguir corriendo.

---

## Terminal 2 – Engine (motor de trading)

El engine se conecta a Deriv, recibe ticks de R_75 y puede abrir trades.

1. Abre una **segunda** terminal.
2. Ve a la misma carpeta del backend:
   ```powershell
   cd "c:\Users\POXIFLOW\Documents\TRABAJOS\bot de trading\botTrading\backend"
   ```
3. Arranca el engine:
   ```powershell
   .\.venv\Scripts\python.exe -m src.app.main engine
   ```
4. Deberías ver: conexión a Deriv, balance, suscripción a ticks, y cada minuto `candle_closed` con indicadores.
5. **Deja esta terminal abierta.** El engine debe seguir corriendo para que haya datos en tiempo real.

---

## Terminal 3 – Frontend (interfaz web)

La web consume la API para mostrar métricas, trades y kill switch.

1. Abre una **tercera** terminal.
2. Ve a la carpeta del frontend (donde está `package.json`):
   ```powershell
   cd "c:\Users\POXIFLOW\Documents\TRABAJOS\bot de trading\botTrading\frontend\frontend"
   ```
3. Si es la primera vez, instala dependencias:
   ```powershell
   npm install
   ```
4. Arranca el servidor de desarrollo:
   ```powershell
   npm run dev
   ```
5. Debe salir algo como: `Local: http://localhost:5173/`
6. **Abre el navegador** en: **http://localhost:5173**
7. **Deja esta terminal abierta** mientras uses la interfaz.

---

## Resumen rápido

| Terminal | Comando (desde la carpeta indicada) | Qué hace |
|----------|--------------------------------------|----------|
| **1 – API** | `cd ...\botTrading\backend` → `.\.venv\Scripts\python.exe -m src.app.main api` | API en http://localhost:8000 |
| **2 – Engine** | `cd ...\botTrading\backend` → `.\.venv\Scripts\python.exe -m src.app.main engine` | Conecta a Deriv, opera R_75, escribe métricas y trades |
| **3 – Frontend** | `cd ...\botTrading\frontend\frontend` → `npm run dev` | Web en http://localhost:5173 |

---

## Qué verás en el frontend

- **Estado / Health** – Si la API responde.
- **Métricas** – Balance, velas cerradas, último precio, indicadores (cuando el engine esté corriendo).
- **Trades** – Historial de operaciones (se llena cuando el engine abre/cierra trades).
- **Kill switch** – Activar/desactivar para pausar que el engine abra nuevos trades.

---

## Parar todo

- En cada terminal: **Ctrl+C**.
- Orden no importa; puedes cerrar frontend, luego engine, luego API (o al revés).

---

## Si algo falla

- **Frontend no muestra datos:** Comprueba que la **API** (Terminal 1) y el **Engine** (Terminal 2) estén corriendo.
- **API no arranca:** Revisa que en `backend` existan `config/default.yaml` y `.env` con el token de Deriv.
- **Engine no conecta:** Revisa el token en `.env` (cuenta DEMO).
- **Frontend “npm run dev” falla:** Ejecuta `npm install` dentro de `botTrading\frontend\frontend`.
