@echo off
setlocal
REM Установка Windows-службы через NSSM.
REM 1) Скачайте nssm.exe (https://nssm.cc/download) и положите рядом или в PATH.
REM 2) Запускайте от имени администратора из корня проекта.

set "APP_DIR=%~dp0.."
pushd "%APP_DIR%"
set "APP_DIR=%CD%"
popd

set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
set "SERVICE_NAME=ADPasswordNotifier"
set "NSSM=nssm"

where nssm >nul 2>&1
if errorlevel 1 (
  if exist "%~dp0nssm.exe" (
    set "NSSM=%~dp0nssm.exe"
  ) else (
    echo [ERROR] nssm.exe не найден. Скачайте NSSM и добавьте в PATH или в scripts\
    exit /b 1
  )
)

if not exist "%PYTHON%" (
  echo [ERROR] Не найден %PYTHON%
  echo Создайте venv: py -3.11 -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

"%NSSM%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM%" remove "%SERVICE_NAME%" confirm >nul 2>&1

"%NSSM%" install "%SERVICE_NAME%" "%PYTHON%" "main.py --serve"
"%NSSM%" set "%SERVICE_NAME%" AppDirectory "%APP_DIR%"
"%NSSM%" set "%SERVICE_NAME%" DisplayName "AD Password Notifier"
"%NSSM%" set "%SERVICE_NAME%" Description "Проверка сроков паролей AD, web UI и рассылка уведомлений"
"%NSSM%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM%" set "%SERVICE_NAME%" AppStdout "%APP_DIR%\logs\service_stdout.log"
"%NSSM%" set "%SERVICE_NAME%" AppStderr "%APP_DIR%\logs\service_stderr.log"
"%NSSM%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM%" set "%SERVICE_NAME%" AppRotateBytes 2097152

"%NSSM%" start "%SERVICE_NAME%"
echo.
echo Служба %SERVICE_NAME% установлена и запущена.
echo Web UI по умолчанию: http://127.0.0.1:8787/
echo Учётку службы задайте в services.msc (Log On) — доменная с read LDAP.
endlocal
