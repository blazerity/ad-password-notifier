@echo off
setlocal
set "SERVICE_NAME=ADPasswordNotifier"
set "NSSM=nssm"

where nssm >nul 2>&1
if errorlevel 1 (
  if exist "%~dp0nssm.exe" (
    set "NSSM=%~dp0nssm.exe"
  ) else (
    echo [ERROR] nssm.exe не найден
    exit /b 1
  )
)

"%NSSM%" stop "%SERVICE_NAME%"
"%NSSM%" remove "%SERVICE_NAME%" confirm
echo Служба %SERVICE_NAME% удалена.
endlocal
