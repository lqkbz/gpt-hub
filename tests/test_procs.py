import sys
import time

from core.procs import classify_codex_error, run_process

PY = sys.executable


async def test_ok_output():
    r = await run_process([PY, "-c", "print('hi')"], timeout=10)
    assert (r.returncode, r.stdout.strip(), r.timed_out) == (0, "hi", False)


async def test_nonzero():
    r = await run_process([PY, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"], timeout=10)
    assert r.returncode == 3 and r.stderr == "bad" and not r.timed_out


async def test_timeout_kills():
    t0 = time.monotonic()
    r = await run_process([PY, "-c", "import time; time.sleep(5)"], timeout=0.5)
    assert r.timed_out
    assert time.monotonic() - t0 < 3


async def test_cwd(tmp_path):
    r = await run_process([PY, "-c", "import os; print(os.getcwd())"], cwd=str(tmp_path), timeout=10)
    assert r.stdout.strip().lower() == str(tmp_path).lower()


def test_classify():
    assert "codex login --device-auth" in classify_codex_error("Error: 401 Unauthorized")
    assert "codex login --device-auth" in classify_codex_error("Not logged in")
    assert "额度" in classify_codex_error("You've hit your usage limit")
    assert "额度" in classify_codex_error("HTTP 429 Too Many Requests")
    assert classify_codex_error("line1\nsomething broke\n") == "something broke"
    assert len(classify_codex_error("x" * 500)) == 200
    assert classify_codex_error("") == "未知错误"
