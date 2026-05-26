@echo off
REM circle-llc — local dev launcher (Windows)
REM Starts: FastAPI backend, Next.js dashboard, Next.js landing
REM Each in its own console window so you can see logs/stop independently.

setlocal
set ROOT=%~dp0

echo.
echo === circle-llc local dev ===
echo Root: %ROOT%
echo.

echo [1/3] Starting FastAPI backend on http://localhost:8000 ...
start "circle-llc API" cmd /k "cd /d %ROOT% && python -m uvicorn orchestrator.api:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Dashboard on http://localhost:3001 ...
start "circle-llc Dashboard" cmd /k "cd /d %ROOT%dashboard && set NEXT_PUBLIC_API_URL=http://localhost:8000&& npm run dev"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Landing on http://localhost:3000 ...
start "circle-llc Landing" cmd /k "cd /d %ROOT%landing && set NEXT_PUBLIC_API_URL=http://localhost:8000&& npm run dev"

echo.
echo All 3 services starting in separate windows.
echo.
echo  - API:        http://localhost:8000/docs    (Swagger)
echo  - Dashboard:  http://localhost:3001
echo  - Landing:    http://localhost:3000
echo  - Factory:    http://localhost:3000/f/techpulse-latam
echo.
echo Close the 3 console windows to stop everything.
echo.
pause
