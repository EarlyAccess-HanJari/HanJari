"""Run with the backend requirements installed; no provider calls or credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MAIN = Path(__file__).with_name("main.py").resolve()
ML = MAIN.parents[2] / "hanjari-ml"


class BackendStartup(unittest.TestCase):
    def start(self, cwd, ml=None):
        env = dict(os.environ, HANJARI_MODE="sample", PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        env.pop("HANJARI_ML", None)
        if ml is not None:
            env["HANJARI_ML"] = str(ml)
        code = '''
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('backend_check', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def forbidden(*args, **kwargs):
    raise AssertionError('test must not call the provider')
module.serve.C.fetch = forbidden
rows = module._predict(0)
assert len(rows) == 6
assert all(row['p_board'] is None for row in rows)
print(json.dumps({'ml': str(module.ML), 'rows': len(rows)}))
'''
        result = subprocess.run([sys.executable, "-c", code, str(MAIN)], cwd=cwd, env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_default_ml_location_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.start(folder)["ml"], str(ML))

    def test_explicit_ml_override_still_takes_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            alternative = Path(folder) / "alternate-ml"
            alternative.symlink_to(ML, target_is_directory=True)
            self.assertEqual(self.start(folder, alternative)["ml"], str(alternative))


if __name__ == "__main__":
    unittest.main()
