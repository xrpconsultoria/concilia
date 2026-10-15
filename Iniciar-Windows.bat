@echo off
setlocal
cd /d "%~dp0"
echo Concilia - teste local
where py >nul 2>nul
if errorlevel 1 (
  set "CONCILIA_PYTHON=python"
) else (
  set "CONCILIA_PYTHON=py -3.12"
)
%CONCILIA_PYTHON% -c "import sys; assert sys.version_info >= (3,12)" >nul 2>nul
if errorlevel 1 (
  echo Instale o Python 3.12 pelo site oficial python.org e habilite Add Python to PATH.
  echo Depois abra este arquivo novamente.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  %CONCILIA_PYTHON% -m venv .venv
  if errorlevel 1 goto :erro
)
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
if errorlevel 1 goto :erro
echo.
echo Quando o servidor iniciar, abra no navegador o endereco mostrado em Running on.
echo Mantenha esta janela aberta durante o uso. Para encerrar, pressione Ctrl+C.
.venv\Scripts\python.exe app.py
if errorlevel 1 goto :erro
exit /b 0
:erro
echo Nao foi possivel iniciar. Copie a mensagem de erro para solicitar ajuda.
pause
exit /b 1
