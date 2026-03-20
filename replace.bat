@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%mizTrans"
set "EXITCODE=0"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Virtual environment mizTrans not found. Creating it...
    py -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        set "EXITCODE=1"
        goto :END
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    set "EXITCODE=1"
    goto :END
)

python "%SCRIPT_DIR%replace.py" %*
if errorlevel 1 (
    echo [ERROR] replace.py exited with an error.
    set "EXITCODE=1"
) else (
    echo [OK] replace.py finished.
)

:END
echo.
pause
endlocal & exit /b %EXITCODE%
