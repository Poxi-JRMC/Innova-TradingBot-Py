# Frontend (Dashboard) – esqueleto

Este directorio queda preparado para un Dashboard en React + Vite + TypeScript.

## Siguiente paso

1) Crear el proyecto:

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm i
npm i -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm i recharts
```

2) Conectar a la API:
- `GET http://localhost:8000/status`
- `GET http://localhost:8000/metrics`
- `GET/POST http://localhost:8000/killswitch`

> Nota: no instalo nada automáticamente para no tocar tu entorno Node sin confirmación.

