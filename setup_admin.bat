@echo off
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe" (
 "%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe" setup_admin.py
) else (
 py setup_admin.py
)
