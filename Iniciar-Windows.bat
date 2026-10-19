@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
echo Concilia v0.5.3 - iniciar
echo Pasta: "%CD%"

rem O bootstrap pode rodar com Python novo; ele seleciona o 3.12 para o aplicativo.
set "CONCILIA_PYTHON="
call :tentar_python py -3.12
if defined CONCILIA_PYTHON goto :iniciar
call :tentar_python py -3
if defined CONCILIA_PYTHON goto :iniciar
call :tentar_python python
if defined CONCILIA_PYTHON goto :iniciar
call :tentar_python python3
if defined CONCILIA_PYTHON goto :iniciar
if defined LOCALAPPDATA call :tentar_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined CONCILIA_PYTHON goto :iniciar
if defined ProgramFiles call :tentar_python "%ProgramFiles%\Python312\python.exe"
if defined CONCILIA_PYTHON goto :iniciar

rem Reutilize o Python local somente se for compativel; ele nao precisara ser movido.
if exist ".venv\Scripts\python.exe" .venv\Scripts\python.exe -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>nul
if not errorlevel 1 if exist ".venv\Scripts\python.exe" set "CONCILIA_PYTHON=.venv\Scripts\python.exe"
if defined CONCILIA_PYTHON goto :iniciar

echo.
echo Instale Python 3.12 de 64 bits para usar o Concilia.
echo Acesse https://www.python.org/downloads/release/python-31210/
echo Em Files, escolha Windows installer (64-bit).
echo Depois abra Iniciar-Windows.bat novamente. Sua pasta data sera preservada.
pause
exit /b 1

:tentar_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
if not errorlevel 1 set "CONCILIA_PYTHON=%*"
exit /b 0

:iniciar
%CONCILIA_PYTHON% iniciar.py
if errorlevel 1 (
  echo.
  echo O Concilia nao iniciou. Siga a orientacao acima ou copie a mensagem para solicitar ajuda.
  pause
  exit /b 1
)
exit /b 0
