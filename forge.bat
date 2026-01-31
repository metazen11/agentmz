@echo off
setlocal
set "PYTHON=python"
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON=%~dp0venv\Scripts\python.exe"

"%PYTHON%" "%~dp0forge\cli.py" %*
endlocal
