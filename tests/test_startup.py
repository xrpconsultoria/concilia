"""Seleção de Python e reparo reversível do ambiente, sem documentos reais."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import iniciar


def runtime(version=(3, 12, 10), bits=64, executable="python-compativel"):
    return iniciar.PythonRuntime((executable,), version, bits, executable)


class PythonSelectionTests(unittest.TestCase):
    def test_only_python312_64bit_can_install_application_dependencies(self):
        self.assertTrue(runtime().compatible)
        for version, bits in [((3, 13, 0), 64), ((3, 14, 0), 64), ((3, 11, 0), 64), ((3, 12, 0), 32)]:
            with self.subTest(version=version, bits=bits):
                self.assertFalse(runtime(version, bits).compatible)

    def test_newer_python_is_skipped_and_python312_selected(self):
        with patch("iniciar.candidates", return_value=iter([("newer",), ("newer",), ("supported",)])), patch("iniciar.probe", side_effect=[runtime((3, 14, 0)), runtime()]) as probe:
            self.assertTrue(iniciar.find_python().compatible)
            self.assertEqual(probe.call_count, 2)
            self.assertEqual(probe.call_args.args[0], ("supported",))

    def test_missing_runtime_explains_exact_version_and_keeps_other_versions(self):
        with patch("iniciar.candidates", return_value=iter([("python",)])), patch("iniciar.probe", return_value=runtime((3, 13, 0))):
            with self.assertRaises(iniciar.StartupError) as error:
                iniciar.find_python()
        for text in ["3.12", "64 bits", "Windows installer (64-bit)", "outras versoes", "data"]:
            self.assertIn(text, str(error.exception))

    def test_probe_handles_missing_interpreter_timeout_and_non_python_command(self):
        for failure in [OSError("missing"), subprocess.TimeoutExpired("python", 10)]:
            with patch("iniciar.subprocess.run", side_effect=failure):
                self.assertIsNone(iniciar.probe(("python",)))
        for result in [Mock(returncode=1), Mock(returncode=0, stdout="not json")]:
            with patch("iniciar.subprocess.run", return_value=result):
                self.assertIsNone(iniciar.probe(("python",)))

    def test_windows_registry_and_known_install_paths_are_candidates(self):
        with patch("iniciar.IS_WINDOWS", True), patch("iniciar.windows_installations", return_value=iter([("registry-python",)])), patch.dict("os.environ", {"LOCALAPPDATA": "/local", "ProgramFiles": "/programs"}):
            candidates = list(iniciar.candidates())
        self.assertIn(("py", "-3.12"), candidates)
        self.assertIn(("registry-python",), candidates)
        self.assertIn((str(Path('/local/Programs/Python/Python312/python.exe')),), candidates)

    def test_registry_executable_path_is_read_without_requiring_path(self):
        key = Mock(); key.__enter__ = Mock(return_value=key);key.__exit__ = Mock(return_value=False)
        registry = types.SimpleNamespace(HKEY_CURRENT_USER=1,HKEY_LOCAL_MACHINE=2,KEY_WOW64_64KEY=256,KEY_WOW64_32KEY=512,KEY_READ=1,OpenKey=Mock(return_value=key),QueryValueEx=Mock(return_value=("python312-registry.exe", 1)))
        with patch("iniciar.IS_WINDOWS", True), patch.dict("sys.modules", {"winreg": registry}):
            paths = list(iniciar.windows_installations())
        self.assertEqual(paths, [("python312-registry.exe",)] * 4)


class EnvironmentRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.environment = self.project / ".venv"
        self.target = iniciar.venv_python(self.project)
        self.target.parent.mkdir(parents=True)
        self.target.write_text("old interpreter marker")
        self.data = self.project / "data" / "sentinel.txt"
        self.data.parent.mkdir(); self.data.write_text("DADOS FICTICIOS PRESERVADOS")

    def tearDown(self):
        self.temp.cleanup()

    def test_compatible_environment_is_reused_without_recreating_or_searching_global_python(self):
        with patch("iniciar.probe", return_value=runtime()), patch("iniciar.find_python") as find, patch("iniciar.run_step") as run, redirect_stdout(StringIO()):
            self.assertEqual(iniciar.prepare_environment(self.project), self.target)
        find.assert_not_called();run.assert_not_called()
        self.assertFalse(list(self.project.glob('.venv-backup-*')))

    def test_incompatible_environment_is_backed_up_and_data_never_moved(self):
        def create(command, message, project):
            self.target.parent.mkdir(parents=True)
            self.target.write_text("new interpreter marker")
        with patch("iniciar.probe", side_effect=[runtime((3, 13, 0)), runtime()]), patch("iniciar.find_python", return_value=runtime()), patch("iniciar.run_step", side_effect=create), redirect_stdout(StringIO()):
            iniciar.prepare_environment(self.project)
        backups = list(self.project.glob('.venv-backup-*'))
        self.assertEqual(len(backups), 1)
        relative = self.target.relative_to(self.environment)
        self.assertEqual((backups[0] / relative).read_text(), "old interpreter marker")
        self.assertEqual(self.target.read_text(), "new interpreter marker")
        self.assertEqual(self.data.read_text(), "DADOS FICTICIOS PRESERVADOS")

    def test_no_compatible_python_leaves_original_environment_and_data_untouched(self):
        with patch("iniciar.probe", return_value=runtime((3, 14, 0))), patch("iniciar.find_python", side_effect=iniciar.StartupError("Instale 3.12")), patch("iniciar.run_step") as run:
            with self.assertRaises(iniciar.StartupError):
                iniciar.prepare_environment(self.project)
        run.assert_not_called()
        self.assertEqual(self.target.read_text(), "old interpreter marker")
        self.assertEqual(self.data.read_text(), "DADOS FICTICIOS PRESERVADOS")
        self.assertFalse(list(self.project.glob('.venv-backup-*')))

    def test_failed_creation_preserves_backup_and_data(self):
        with patch("iniciar.probe", return_value=None), patch("iniciar.find_python", return_value=runtime()), patch("iniciar.run_step", side_effect=iniciar.StartupError("Falhou")), redirect_stdout(StringIO()):
            with self.assertRaises(iniciar.StartupError):
                iniciar.prepare_environment(self.project)
        self.assertEqual(len(list(self.project.glob('.venv-backup-*'))), 1)
        self.assertEqual(self.data.read_text(), "DADOS FICTICIOS PRESERVADOS")

    def test_windows_interpreter_path_uses_scripts_directory(self):
        with patch("iniciar.IS_WINDOWS", True):
            self.assertEqual(iniciar.venv_python(self.project), self.project / '.venv' / 'Scripts' / 'python.exe')


class StartupFlowTests(unittest.TestCase):
    def test_command_failures_show_exit_code_or_system_cause(self):
        for failure, detail in [(subprocess.CalledProcessError(7, ["python"]), "codigo 7"), (OSError("sem permissao"), "sem permissao")]:
            with self.subTest(detail=detail), patch("iniciar.subprocess.run", side_effect=failure), redirect_stdout(StringIO()):
                with self.assertRaises(iniciar.StartupError) as error:
                    iniciar.run_step(("python",), "Instalando...", Path.cwd())
                self.assertIn(detail, str(error.exception))
                self.assertIn("data", str(error.exception))

    def test_prepare_only_installs_and_verifies_with_the_selected_interpreter(self):
        with patch("iniciar.prepare_environment", return_value=Path("selected-python")), patch("iniciar.run_step") as run:
            self.assertEqual(iniciar.main(["--preparar"]), 0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(command[0] == "selected-python" for command in commands))
        self.assertIn("--only-binary=:all:", commands[0])
        self.assertNotIn("app.py", str(commands))

    def test_install_failure_cannot_launch_application(self):
        with patch("iniciar.prepare_environment", return_value=Path("selected-python")), patch("iniciar.run_step", side_effect=iniciar.StartupError("Instalacao falhou")) as run, redirect_stderr(StringIO()):
            self.assertEqual(iniciar.main([]), 1)
        self.assertEqual(run.call_count, 1)

    def test_default_flow_starts_app_only_after_all_checks(self):
        with patch("iniciar.prepare_environment", return_value=Path("selected-python")), patch("iniciar.run_step") as run, redirect_stdout(StringIO()):
            self.assertEqual(iniciar.main([]), 0)
        self.assertEqual(run.call_count, 4)
        self.assertEqual(run.call_args.args[0], ("selected-python", str(iniciar.ROOT / 'app.py')))


if __name__ == "__main__":
    unittest.main()
