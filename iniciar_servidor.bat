@echo off
title Servidor Central de Consecutivos y Padron CENAM
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo =======================================================================
echo   CENTRO NACIONAL DE METROLOGIA - CENAM
echo   Servidor Central de Consecutivos y Padron Metrologico (Multilocacion)
echo =======================================================================
echo.

:LOCALIZAR_PYTHON
:: 1. LOCALIZAR PYTHON
set "PYTHON_EXE="

:: 1.1 Entorno virtual local
if exist "%~dp0env\Scripts\python.exe" set "PYTHON_EXE=%~dp0env\Scripts\python.exe"
if exist "%~dp0..\env\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\env\Scripts\python.exe"

:: 1.2 Rutas habituales directas en C:\
if "!PYTHON_EXE!"=="" if exist "C:\Python314\python.exe" set "PYTHON_EXE=C:\Python314\python.exe"
if "!PYTHON_EXE!"=="" if exist "C:\Python312\python.exe" set "PYTHON_EXE=C:\Python312\python.exe"
if "!PYTHON_EXE!"=="" if exist "C:\Python311\python.exe" set "PYTHON_EXE=C:\Python311\python.exe"
if "!PYTHON_EXE!"=="" if exist "C:\Python310\python.exe" set "PYTHON_EXE=C:\Python310\python.exe"

:: 1.3 LocalAppData
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python314\python.exe"
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python310\python.exe"
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_EXE=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
if "!PYTHON_EXE!"=="" if exist "%LocalAppData%\Python\bin\python.exe" set "PYTHON_EXE=%LocalAppData%\Python\bin\python.exe"

:: 1.4 ProgramFiles
if "!PYTHON_EXE!"=="" if exist "%ProgramFiles%\Python314\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python314\python.exe"
if "!PYTHON_EXE!"=="" if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
if "!PYTHON_EXE!"=="" if exist "%ProgramFiles%\Python311\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python311\python.exe"
if "!PYTHON_EXE!"=="" if exist "%ProgramFiles%\Python310\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python310\python.exe"

:: 1.5 Probar py launcher
if "!PYTHON_EXE!"=="" (
    py -3 -c "import sys; sys.exit(0)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=py -3"
)

:: 1.6 Probar comando python en PATH
if "!PYTHON_EXE!"=="" (
    python -c "import sys; sys.exit(0 if sys.version_info[0]==3 and sys.version_info[1]>=9 else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if "!PYTHON_EXE!"=="" (
    echo =======================================================================
    echo   [ERROR CRITICO] No se encontro Python en el sistema.
    echo =======================================================================
    echo Por favor ejecute primero: instalar_offline.bat
    echo =======================================================================
    echo.
    pause
    exit /b 1
)

:: 2. VERIFICAR SI YA ESTA ACTIVO EN EL PUERTO 8001
netstat -ano | findstr :8001 | findstr LISTENING >nul 2>&1
if not errorlevel 1 (
    echo =======================================================================
    echo   [*] El servidor de consecutivos ya esta ACTIVO en http://127.0.0.1:8001
    echo =======================================================================
    echo Abriendo el panel de administracion en el navegador web...
    start "" "http://127.0.0.1:8001"
    echo.
    echo Opciones:
    echo   [R] Reiniciar el servidor (cerrar proceso previo y reiniciar)
    echo   [Enter] Salir (mantener el servidor actual activo)
    echo.
    set /p "OPC_SRV=Seleccione una opcion [R / Enter]: "
    if /i "!OPC_SRV!"=="R" (
        echo [*] Cerrando proceso previo en puerto 8001...
        for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        ping -n 2 127.0.0.1 >nul
        goto INICIAR_SRV
    )
    exit /b 0
)

:INICIAR_SRV
:: 3. VERIFICAR DEPENDENCIAS
!PYTHON_EXE! -c "import fastapi, uvicorn, pydantic, jinja2" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Faltan librerias para el servidor de consecutivos.
    echo Instalando dependencias necesarias...
    if exist "%~dp0instalar_offline.bat" call "%~dp0instalar_offline.bat"
    if exist "%~dp0..\instalar_offline.bat" call "%~dp0..\instalar_offline.bat"
)

:: 4. INICIAR MICROSERVICIO
echo [*] Iniciando Servidor Central CENAM en http://0.0.0.0:8001 ...
echo [*] Accesible localmente en: http://127.0.0.1:8001
echo [*] Para detener el servidor, cierre esta ventana o presione Ctrl + C.
echo.

:: Abrir navegador de forma nativa
start "" "http://127.0.0.1:8001"

if exist "main_consecutivos.py" (
    !PYTHON_EXE! -m uvicorn main_consecutivos:app --host 0.0.0.0 --port 8001
) else if exist "servidor_consecutivos\main_consecutivos.py" (
    !PYTHON_EXE! -m uvicorn servidor_consecutivos.main_consecutivos:app --host 0.0.0.0 --port 8001
) else (
    echo [ERROR CRITICO] No se encontro el archivo 'main_consecutivos.py'.
    pause
    exit /b 1
)

if errorlevel 1 (
    echo.
    echo =======================================================================
    echo   [ERROR AL INICIAR EL SERVIDOR DE CONSECUTIVOS]
    echo =======================================================================
    echo El servidor no pudo iniciar o el puerto 8001 esta ocupado.
    echo =======================================================================
    echo.
    pause
)
