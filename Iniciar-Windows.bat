@echo off
setlocal
cd /d "%~dp0"
echo Concilia - teste local

rem Reutilize um ambiente existente sem exigir o launcher global.
if exist ".venv\Scripts\python.exe" goto :validar_ambiente

rem O launcher pode existir sem ter especificamente a versao 3.12.
set "CONCILIA_PYTHON="
call :tentar_python py -3.12
if defined CONCILIA_PYTHON goto :criar_ambiente
call :tentar_python py -3
if defined CONCILIA_PYTHON goto :criar_ambiente
call :tentar_python python
if defined CONCILIA_PYTHON goto :criar_ambiente
call :tentar_python python3
if defined CONCILIA_PYTHON goto :criar_ambiente

echo.
echo Nenhum Python 3.12 ou superior foi encontrado.
echo 1. Acesse https://www.python.org/downloads/windows/
echo 2. Instale uma versao Python 3.12 ou superior.
echo 3. Se o instalador mostrar Add python.exe to PATH, marque essa opcao.
echo 4. Feche esta janela e abra Iniciar-Windows.bat novamente.
echo.
echo Se voce ja instalou o Python, envie o resultado de: py --list
echo E tambem de: python --version
pause
exit /b 1

:tentar_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 set "CONCILIA_PYTHON=%*"
exit /b 0

:criar_ambiente
echo Python encontrado: %CONCILIA_PYTHON%
%CONCILIA_PYTHON% -m venv .venv
if errorlevel 1 goto :erro

:validar_ambiente
.venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 (
  echo O ambiente em .venv nao funciona ou usa um Python anterior ao 3.12.
  echo Extraia o projeto em uma nova pasta e tente novamente. Preserve a pasta data se ja cadastrou informacoes.
  goto :erro
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
