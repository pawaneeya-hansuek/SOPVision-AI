@echo off
setlocal
cd /d "%~dp0"
set "SOPVISION_PYTHON="
if exist ".venv\Scripts\python.exe" set "SOPVISION_PYTHON=%CD%\.venv\Scripts\python.exe"
if defined SOPVISION_PYTHON goto run
for /d %%D in ("%LocalAppData%\Python\pythoncore-*") do if exist "%%~fD\python.exe" set "SOPVISION_PYTHON=%%~fD\python.exe"
if defined SOPVISION_PYTHON goto run
python --version >nul 2>nul
if not errorlevel 1 set "SOPVISION_PYTHON=python"
if defined SOPVISION_PYTHON goto run
echo Python was not found. Install Python, then run this file again.
goto done
:run
"%SOPVISION_PYTHON%" -c "import fastapi,uvicorn,multipart,cv2,numpy,pydantic,cryptography,httpx" >nul 2>nul
if not errorlevel 1 goto ready
"%SOPVISION_PYTHON%" -m pip install -r requirements-mobile.txt
if errorlevel 1 goto done
:ready
"%SOPVISION_PYTHON%" start_mobile.py
:done
pause
endlocal
