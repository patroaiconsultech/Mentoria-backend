import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent.parent
SCRIPT = HERE / "tools" / "audit_backend_modules.py"
spec = importlib.util.spec_from_file_location("dg01_backend_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class BackendModuleAuditTest(unittest.TestCase):
    def test_baseline_database_has_required_api(self):
        path = HERE/"payload"/"backend"/"src"/"orkio_v2"/"database.py"
        content = path.read_text(encoding="utf-8")
        for term in ("class Base(", "def normalize_database_url(", "def make_engine(", "SessionLocal =", "def get_db("):
            self.assertIn(term, content)

    def test_missing_direct_relative_import_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/"src"/"orkio_v2"
            src.mkdir(parents=True)
            (src/"main.py").write_text("from .database import Base\nfrom .config import get_settings\n")
            (src/"config.py").write_text("pass\n")
            self.assertEqual(mod.main_dependencies(Path(tmp)), ["database"])
            (src/"database.py").write_text("pass\n")
            self.assertEqual(mod.main_dependencies(Path(tmp)), [])

    def test_sha256_inventory_is_exact(self):
        expected=json.loads((HERE/"docs"/"BASELINE_MODULE_SHA256.json").read_text())
        file=HERE/"payload"/"backend"/"src"/"orkio_v2"/"database.py"
        self.assertEqual(mod.sha256_file(file),expected["src/orkio_v2/database.py"])

    def test_audit_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=root/"src"/"orkio_v2"
            src.mkdir(parents=True)
            (src/"main.py").write_text("from .database import Base\n")
            data=mod.audit(root,{"src/orkio_v2/database.py":"x"})
            self.assertEqual(data["missing"],["src/orkio_v2/database.py"])
            self.assertEqual(data["main_imports_missing"],["database"])
            self.assertFalse((src/"database.py").exists())

if __name__=="__main__":
    unittest.main()
