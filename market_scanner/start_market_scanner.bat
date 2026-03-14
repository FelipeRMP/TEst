@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" -c "import fastapi, pandas, httpx, pydantic" >nul 2>nul
if errorlevel 1 set "PYTHON_EXE=python"

if not exist "%ROOT%\frontend\node_modules" (
  echo Installing frontend dependencies...
  call npm.cmd install --prefix "%ROOT%\frontend"
  if errorlevel 1 (
    echo Failed to install frontend dependencies.
    pause
    exit /b 1
  )
)

echo Starting FastAPI backend...
start "Market Scanner Backend" cmd /k "cd /d ""%ROOT%"" && ""%PYTHON_EXE%"" -m uvicorn backend.app.api:app --reload"

echo Starting frontend...
start "Market Scanner Frontend" cmd /k "cd /d ""%ROOT%\frontend"" && npm.cmd run dev"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Two new terminal windows were opened for the backend and frontend.

endlocal
