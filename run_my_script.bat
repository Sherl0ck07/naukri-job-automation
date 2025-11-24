@echo off
SETLOCAL

REM ===== Configuration =====
SET VENV_DIR=resume_transformers
SET REQUIREMENTS=requirements.txt
SET SCRIPT=main.py
SET PYTHON_EXE=C:\Users\imjad\AppData\Local\Programs\Python\Python311\python.exe

REM ===== Check if system Python exists =====
%PYTHON_EXE% --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO System Python not found at %PYTHON_EXE%.
    PAUSE
    EXIT /B 1
)

REM ===== Create virtual environment if it doesn't exist =====
IF NOT EXIST "%VENV_DIR%\" (
    ECHO Creating virtual environment: %VENV_DIR% using system Python...
    %PYTHON_EXE% -m venv %VENV_DIR%
)

REM ===== Activate the virtual environment =====
CALL "%VENV_DIR%\Scripts\activate.bat"

REM ===== Show active Python and pip info =====
ECHO Active Python version:
python --version
ECHO Python executable location:
where python
ECHO Pip version:
pip --version

REM ===== Check if requirements.txt exists =====
IF NOT EXIST "%REQUIREMENTS%" (
    ECHO %REQUIREMENTS% file not found! Please add it and try again.
    PAUSE
    EXIT /B 1
)

REM ===== Check if requirements.txt was modified in last 24 hours =====
FOR %%I IN ("%REQUIREMENTS%") DO SET "REQ_FULLPATH=%%~fI"

REM Use PowerShell to get the time difference in hours between now and file's LastWriteTime
FOR /F %%H IN ('powershell -NoProfile -Command ^
    "(Get-Date) - (Get-Item '%REQ_FULLPATH%').LastWriteTime | Select-Object -ExpandProperty TotalHours"') DO SET HOURS_SINCE_MOD=%%H

REM Remove decimal part by truncation
FOR /F "tokens=1 delims=." %%A IN ("%HOURS_SINCE_MOD%") DO SET HOURS_SINCE_MOD=%%A

ECHO Hours since requirements.txt last modified: %HOURS_SINCE_MOD%

IF %HOURS_SINCE_MOD% GEQ 24 (
    SET REQ_CHANGED=0
    ECHO requirements.txt not modified in last 24 hours. Skipping install.
) ELSE (
    SET REQ_CHANGED=1
    ECHO requirements.txt modified within 24 hours. Installing packages...
)

IF "%REQ_CHANGED%"=="1" (
    pip install --disable-pip-version-check --no-input --quiet --requirement %REQUIREMENTS% --upgrade --exists-action i
)

REM pip freeze > requirements.txt

REM ===== Run your Python script =====
ECHO Running %SCRIPT%...
python -u %SCRIPT%

ECHO Done.
PAUSE
ENDLOCAL
