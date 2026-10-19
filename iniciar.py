"""Inicializador sem dependências, executável por Python 3.8 ou mais novo.

Somente o Python 3.12 de 64 bits cria o ambiente e instala os pacotes do app.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
VERSION = "0.5.3"
REQUIRED_VERSION = (3, 12)
IS_WINDOWS = sys.platform == "win32"
DOWNLOAD_URL = "https://www.python.org/downloads/release/python-31210/"
PROBE = (
    "import json,struct,sys; "
    "print(json.dumps({'version':list(sys.version_info[:3]),"
    "'bits':struct.calcsize('P')*8,'executable':sys.executable},ensure_ascii=True))"
)


class StartupError(Exception):
    pass


@dataclass(frozen=True)
class PythonRuntime:
    command: tuple
    version: tuple
    bits: int
    executable: str

    @property
    def compatible(self):
        return self.version[:2] == REQUIRED_VERSION and self.bits == 64


def probe(command):
    try:
        # Windows launchers/older Python may write cp1252 diagnostics even when
        # this bootstrap defaults to UTF-8. Never decode both pipes implicitly:
        # Windows reader-thread exceptions would otherwise hide valid runtimes.
        result = subprocess.run(list(command) + ["-c", PROBE], capture_output=True, timeout=10)
        if result.returncode:
            return None
        info = json.loads(result.stdout)
        return PythonRuntime(tuple(command), tuple(info["version"]), int(info["bits"]), info["executable"])
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None


def windows_installations():
    """Read standard PEP 514 locations without requiring global PATH."""
    if not IS_WINDOWS:
        return
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            for tag in ("3.12", "3.12-64"):
                try:
                    path = "Software\\Python\\PythonCore\\" + tag + "\\InstallPath"
                    with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
                        try:
                            yield (winreg.QueryValueEx(key, "ExecutablePath")[0],)
                        except OSError:
                            yield (str(Path(winreg.QueryValue(key, None)) / "python.exe"),)
                except OSError:
                    continue


def candidates():
    yield (sys.executable,)
    base = getattr(sys, "_base_executable", None)
    if base:
        yield (base,)
    if IS_WINDOWS:
        yield ("py", "-3.12")
        yield ("py", "-V:3.12")
        yield from windows_installations()
        for variable, suffix in (
            ("LOCALAPPDATA", "Programs/Python/Python312/python.exe"),
            ("LOCALAPPDATA", "Python/pythoncore-3.12-64/python.exe"),
            ("ProgramFiles", "Python312/python.exe"),
        ):
            if os.environ.get(variable):
                yield (str(Path(os.environ[variable]) / suffix),)
    yield ("python3.12",)
    yield ("python3",)
    yield ("python",)


def find_python():
    seen = set()
    for command in candidates():
        if command in seen:
            continue
        seen.add(command)
        runtime = probe(command)
        if runtime and runtime.compatible:
            return runtime
    raise StartupError(
        "Inicializador aberto com Python " + ".".join(map(str, sys.version_info[:3])) + ".\n"
        "Nenhum Python 3.12 de 64 bits foi encontrado nesta busca.\n"
        "O Concilia precisa do Python 3.12 de 64 bits para o OCR.\n"
        "Python 3.13, 3.14 ou mais novo nao e compativel com os pacotes desta versao.\n"
        "1. Acesse " + DOWNLOAD_URL + "\n"
        "2. Em Files, escolha Windows installer (64-bit).\n"
        "3. Instale o Python 3.12 e abra Iniciar-Windows.bat novamente.\n"
        "Se usa o novo gerenciador Python, outra opcao e executar: py install 3.12\n"
        "Voce pode manter outras versoes do Python instaladas. A pasta data sera preservada.\n"
        "No Linux/macOS, instale Python 3.12 de 64 bits e execute o inicializador novamente."
    )


def venv_python(project):
    return project / ".venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def run_step(command, message, project):
    print(message, flush=True)
    try:
        subprocess.run(list(command), cwd=str(project), check=True)
    except subprocess.CalledProcessError as exc:
        raise StartupError(message + f" Falhou (codigo {exc.returncode}). Confira a mensagem acima e tente abrir o inicializador novamente. A pasta data nao foi alterada.") from exc
    except OSError as exc:
        raise StartupError(message + " Nao foi possivel executar o comando: " + str(exc) + ". Confira a instalacao do Python e a permissao de escrita na pasta do projeto. A pasta data nao foi alterada.") from exc


def prepare_environment(project):
    target = venv_python(project)
    existing = probe((str(target),)) if target.is_file() else None
    if existing and existing.compatible:
        print("Ambiente existente: Python 3.12 de 64 bits.", flush=True)
        return target
    # Find a supported interpreter before moving anything in the installation.
    runtime = find_python()
    print("Python compativel: " + runtime.executable, flush=True)
    environment = project / ".venv"
    if environment.exists() or environment.is_symlink():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = project / (".venv-backup-" + stamp + "-" + uuid.uuid4().hex[:8])
        try:
            environment.rename(backup)
        except OSError as exc:
            raise StartupError("Nao foi possivel mover o ambiente antigo. Feche as outras janelas do Concilia e terminais que estejam usando .venv; depois abra o inicializador novamente. A pasta data nao foi alterada.") from exc
        print("Ambiente antigo preservado em " + backup.name, flush=True)
    run_step(runtime.command + ("-m", "venv", str(environment)), "Preparando ambiente Python 3.12...", project)
    created = probe((str(target),))
    if not created or not created.compatible:
        raise StartupError("O ambiente criado nao usa Python 3.12 de 64 bits. O aplicativo nao foi iniciado. Confira a instalacao do Python 3.12; a pasta data esta preservada.")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description="Instala e inicia o Concilia com Python 3.12 de 64 bits.")
    parser.add_argument("--preparar", action="store_true", help="Instala e verifica as dependencias, sem iniciar o servidor.")
    args = parser.parse_args(argv)
    print("Inicializador Concilia v" + VERSION, flush=True)
    print("Pasta do aplicativo: " + str(ROOT), flush=True)
    print("Python do inicializador: " + ".".join(map(str, sys.version_info[:3])), flush=True)
    try:
        python = prepare_environment(ROOT)
        run_step((str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--only-binary=:all:", "-r", str(ROOT / "requirements.txt")), "Instalando dependencias do Concilia...", ROOT)
        run_step((str(python), "-m", "pip", "check"), "Conferindo dependencias...", ROOT)
        run_step((str(python), "-c", "import flask, openpyxl, pypdf, rapidocr_onnxruntime, pypdfium2"), "Verificando bibliotecas do aplicativo e OCR local...", ROOT)
        if not args.preparar:
            print("Abra no navegador o endereco mostrado em Running on. Mantenha esta janela aberta; Ctrl+C encerra o aplicativo.", flush=True)
            run_step((str(python), str(ROOT / "app.py")), "Iniciando Concilia...", ROOT)
        return 0
    except StartupError as exc:
        print("\n" + str(exc), file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
