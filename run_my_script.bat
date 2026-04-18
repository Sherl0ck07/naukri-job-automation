@echo off
SETLOCAL

REM ===== Configuration =====
SET VENV_DIR=resume_transformers
SET SCRIPT=core\main.py

REM ===== Create virtual environment if it doesn't exist =====
IF NOT EXIST "%VENV_DIR%\" (
    ECHO Creating virtual environment: %VENV_DIR%...
    python -m venv %VENV_DIR%
)

REM ===== Activate the virtual environment =====
CALL "%VENV_DIR%\Scripts\activate.bat"

REM ===== Run your Python script =====
ECHO Running %SCRIPT%...
python -u %SCRIPT%

ECHO Done.
PAUSE
ENDLOCAL