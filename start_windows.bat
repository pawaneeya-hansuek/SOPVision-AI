@echo off
setlocal
cd /d "%~dp0"
set "SOPVISION_PYTHON="
if exist ".venv\Scripts\python.exe" set "SOPVISION_PYTHON=%CD%\.venv\Scripts\python.exe"
if defined SOPVISION_PYTHON goto run
py --version >nul 2>nul
if not errorlevel 1 set "SOPVISION_PYTHON=py"
if defined SOPVISION_PYTHON goto run
python --version >nul 2>nul
if not errorlevel 1 set "SOPVISION_PYTHON=python"
if defined SOPVISION_PYTHON goto run
for /d %%D in ("%LocalAppData%\Python\pythoncore-*") do if exist "%%~fD\python.exe" set "SOPVISION_PYTHON=%%~fD\python.exe"
if defined SOPVISION_PYTHON goto run
for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do if exist "%%~fD\python.exe" set "SOPVISION_PYTHON=%%~fD\python.exe"
if defined SOPVISION_PYTHON goto run
echo Python was not found. Install Python, then run this file again.
goto done
:run
echo Using: %SOPVISION_PYTHON%
"%SOPVISION_PYTHON%" -c "import fastapi,uvicorn,multipart,cv2,numpy,pydantic" >nul 2>nul
if not errorlevel 1 goto ready
"%SOPVISION_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto done
:ready
echo Open http://127.0.0.1:8000 in Chrome or Edge.
"%SOPVISION_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --no-access-log
:done
pause
endlocal
