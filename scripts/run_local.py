"""Run the exported web app with local sample data by default."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['sample', 'latest'], default='sample')
parser.add_argument('--port', type=int, default=8000)
args = parser.parse_args()
root = Path(os.path.abspath(__file__)).parents[1]
env = os.environ.copy()
env['HANJARI_ML'] = str(root / 'hanjari-ml')
env['HANJARI_MODE'] = args.mode
env['PYTHONUTF8'] = '1'
env['PYTHONDONTWRITEBYTECODE'] = '1'
raise SystemExit(subprocess.call([
    sys.executable, '-m', 'uvicorn', 'main:app',
    '--app-dir', str(root / 'hanjari-web/backend'),
    '--host', '127.0.0.1', '--port', str(args.port), '--workers', '1',
], env=env))
