@echo off
echo Starting Ookami Mio v3...
echo.

REM Find the right Python with PySide6
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found in PATH
    pause
    exit /b 1
)

REM Try to run with the current Python
echo Using: %PYTHON%
"%PYTHON%" "Mio_v3/src/main.py" %*

if %errorlevel% neq 0 (
    echo.
    echo =====================================
    echo PYTHON/PYSIDE ISSUE DETECTED
    echo =====================================
    echo.
    echo Trying to install PySide6...
    "%PYTHON%" -m pip install PySide6
    
    echo.
    echo Retrying startup...
    "%PYTHON%" "Mio_v3/src/main.py" %*
)

pause