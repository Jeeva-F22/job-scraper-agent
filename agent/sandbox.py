"""Stage 6a: Sandboxed execution of the generated scraper.

Runs the script as an isolated subprocess with a hard timeout so a bad script
(infinite loop, hung network call) can never hang the agent run.
"""
import subprocess
import sys
import os

TIMEOUT_SEC = 300


def run(script_path, out_dir):
    output_path = os.path.join(out_dir, "output.jsonl")
    try:
        proc = subprocess.run(
            [sys.executable, script_path, output_path],
            cwd=out_dir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
        return {
            "timed_out": False,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "output_path": output_path,
            "output_exists": os.path.exists(output_path),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "timed_out": True,
            "exit_code": None,
            "stdout": (e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
            "stderr": (e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "",
            "output_path": output_path,
            "output_exists": os.path.exists(output_path),
        }
