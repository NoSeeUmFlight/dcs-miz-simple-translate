@echo off
REM Drag and drop one or more .miz files onto this BAT to run the Python script.

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%mizTrans

if exist "%VENV_DIR%\Scripts\python.exe" goto venv_ready

echo Virtual environment mizTrans not found.
echo Creating virtual environment...
py -3 -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
)

:venv_ready
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

python -c "import openai, tqdm" >nul 2>nul
if errorlevel 1 (
    echo Missing dependencies detected. Installing required packages...
    python -m pip install --upgrade pip
    python -m pip install openai tqdm
    if errorlevel 1 (
        echo Failed to install required packages.
        pause
        exit /b 1
    )
)

:loop
if "%~1"=="" goto end

REM %~1 = full file path of the dropped file
python "%SCRIPT_DIR%translate.py" "%~1"

shift
goto loop

:end
pause
