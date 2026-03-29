@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.conda\python.exe"

if not exist "%PYTHON%" (
    set "PYTHON=python"
)

%PYTHON% "%ROOT%scripts\create_database.py" --with-device-pin %*
