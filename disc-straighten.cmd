@echo off
setlocal
set "PYTHONUTF8=1"
if exist "%~dp0.venv\Scripts\python.exe" goto run
where py >nul 2>nul
if errorlevel 1 goto python
py -3 "%~dp0bootstrap.py" %*
exit /b %errorlevel%
:python
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.12+ is required. See WINDOWS.md. 1>&2
  exit /b 1
)
python "%~dp0bootstrap.py" %*
exit /b %errorlevel%
:run
"%~dp0.venv\Scripts\python.exe" "%~dp0bootstrap.py" %*
exit /b %errorlevel%
