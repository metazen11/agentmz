@echo off
REM v2 Startup Script - Windows Batch Wrapper
REM Calls start.ps1 with any passed arguments

PowerShell -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
