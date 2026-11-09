"""Guardas locais do patch de instrumentação do Dockerfile (sem Docker/Railway)."""
import hashlib
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCKER = (ROOT / "payload/backend/Dockerfile").read_bytes()
EXPECTED_OLD = "de24b1539a67ac456403c82039c6308316cd8dfa7e639f3f0f52524c2fd3a005"
OLD_BLOCK = 'RUN python -c "import faster_whisper; print(\'DIAG_FASTER_WHISPER_IMPORT_OK\', flush=True)"'
PYTHON_CMD = (
    'python -u -X faulthandler -c "print(\'DG01_PYTHON_RUNNING\', flush=True); '
    'import faster_whisper; print(\'DIAG_FASTER_WHISPER_IMPORT_OK\', flush=True)"'
)

def diag_shell():
    lines = DOCKER.decode().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("RUN set +e;"))
    end = next(i for i in range(start + 1, len(lines)) if not lines[i].endswith("\\"))
    command = "\n".join(lines[start:end+1]).replace("\\\n", "\n")[4:]
    assert command.count(PYTHON_CMD) == 1
    return command

class DockerDiagTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["/bin/sh", "-n", "-c", diag_shell()], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_preserved_install_and_start_and_import_gate(self):
        text = DOCKER.decode()
        self.assertIn("python -m pip install --no-cache-dir --require-hashes -r requirements.lock.txt", text)
        self.assertIn('CMD ["uvicorn","orkio_v2.main:app","--host","0.0.0.0","--port","8080"]', text)
        self.assertIn("import orkio_v2.main", text)
        self.assertIn('exit "${dg01_rc}"', text)
        self.assertNotIn(OLD_BLOCK, text)

    def test_failure_is_not_masked(self):
        command = diag_shell().replace(PYTHON_CMD, 'python -c "raise SystemExit(37)"')
        result = subprocess.run(["/bin/sh", "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertIn("DG01_STT_IMPORT_EXIT_CODE=37", result.stdout)

    def test_success_path(self):
        command = diag_shell().replace(PYTHON_CMD, 'python -c "print(\'DG01_PYTHON_RUNNING\', flush=True)"')
        result = subprocess.run(["/bin/sh", "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DG01_STT_IMPORT_EXIT_CODE=0", result.stdout)
        self.assertIn("DG01_CGROUP_AFTER", result.stdout)

    def test_only_single_original_run_replaced(self):
        patch = (ROOT / "docs/DOCKERFILE_DIFF.patch").read_text()
        self.assertEqual(patch.count('-RUN python -c "import faster_whisper'), 1)
        self.assertEqual(patch.count('+RUN set +e;'), 1)
        self.assertEqual(DOCKER.count(b"\r\n"), DOCKER.count(b"\n"))

if __name__ == "__main__":
    unittest.main()
