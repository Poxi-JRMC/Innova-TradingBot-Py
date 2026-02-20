# Deriv (DEMO): cómo crear `app_id` y `API token`

> Objetivo: dejar el bot apuntando a **DEMO** por defecto.

## 1) Crear cuenta DEMO / entrar a Deriv

1. Abre: https://app.deriv.com/
2. Inicia sesión.
3. Cambia a cuenta **Demo** (virtual) desde el selector de cuenta.

## 2) Crear `API token`

1. En Deriv, ve a: **Settings → API token**
   - Link directo: https://app.deriv.com/account/api-token
2. Crea un token con permisos mínimos al inicio:
   - Para este MVP (solo leer balance + ticks): **Read**
   - (Cuando implementemos ejecución): necesitaremos **Trade** explícitamente.
3. Copia el token y guárdalo en un lugar seguro.

## 3) Crear `app_id`

1. Ve a: **Settings → API token** (misma pantalla).
2. Busca la sección **App registration** (o “Register application”).
3. Registra una app con un nombre (ej: `botTrading-mvp`).
4. Copia el **app_id** generado.

## 4) Configurar el bot

Edita `config/default.yaml`:

```yaml
deriv:
  app_id: "TU_APP_ID"
  api_token: "TU_API_TOKEN"
```

## 5) Seguridad recomendada

- No commitear tokens.
- Ideal: usar `.env` o un secret manager (cuando pasemos a Docker/CI).
- Rotar token si sospechas exposición.

