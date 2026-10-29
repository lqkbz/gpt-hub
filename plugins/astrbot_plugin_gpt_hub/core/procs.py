"""子进程运行（超时杀进程树）与 codex 错误归类。"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


Runner = Callable[..., Awaitable[ProcResult]]

_POSIX = sys.platform != "win32"


def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if _POSIX:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


async def run_process(
    argv: list[str],
    *,
    cwd: str | None = None,
    timeout: float,
    env: dict | None = None,
) -> ProcResult:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=_POSIX,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        _kill(proc)
        out, err = await proc.communicate()
        return ProcResult(proc.returncode or -1, _decode(out), _decode(err), True)
    except asyncio.CancelledError:
        _kill(proc)
        await proc.wait()
        raise
    return ProcResult(proc.returncode, _decode(out), _decode(err), False)


def _decode(b: bytes | None) -> str:
    return (b or b"").decode("utf-8", errors="replace")


_LOGIN_HINTS = ("401", "unauthorized", "not logged in", "login", "log in", "auth")
_LIMIT_HINTS = ("usage limit", "rate limit", "429", "quota")


def classify_codex_error(stderr: str) -> str:
    low = stderr.lower()
    if any(h in low for h in _LIMIT_HINTS):
        return "订阅额度已用尽或被限流，请稍后再试"
    if any(h in low for h in _LOGIN_HINTS):
        return "Codex 未登录或凭据失效，请 owner 在服务器执行 codex login --device-auth"
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    return lines[-1][:200] if lines else "未知错误"
