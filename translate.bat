@echo off
REM Drag and drop one or more .miz files onto this BAT to run the Python script.

set SCRIPT_DIR=%~dp0

:loop
if "%~1"=="" goto end

REM %~1 = full file path of the dropped file
python "%SCRIPT_DIR%translate.py" "%~1"

shift
goto loop

:end
pause
