@echo off
setlocal
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0bootstrap.py" --gui %*
) else (
  py -3 "%~dp0bootstrap.py" --gui %*
)
exit /b %errorlevel%
