@echo off
cd /d "%~dp0"
echo Iniciando API en http://127.0.0.1:8000 ...
echo.
.\.venv\Scripts\python.exe -m src.app.main api
pause
