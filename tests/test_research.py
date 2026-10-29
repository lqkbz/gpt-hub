import asyncio
from pathlib import Path

import pytest

from core.config import parse_config
from core.procs import ProcResult
from core.research import ResearchService
from core.store import Store


class Notes:
    def __init__(self):
        self.calls = []
        self.event = asyncio.Event()

    async def __call__(self, umo, text, file_path):
        self.calls.append((umo, text, file_path))
        self.event.set()

    async def wait(self, n=1, timeout=3):
        async def _w():
            while len(self.calls) < n:
                self.event.clear()
                await self.event.wait()

        await asyncio.wait_for(_w(), timeout)


def report_dir(argv):
    return Path(argv[argv.index("-o") + 1])


def runner_writing(text, rc=0, timed_out=False, stderr=""):
    async def run(argv, *, cwd=None, timeout, env=None):
        if text is not None:
            report_dir(argv).write_text(text, encoding="utf-8")
        return ProcResult(rc, "", stderr, timed_out)

    return run


def blocking_runner():
    started = asyncio.Event()

    async def run(argv, *, cwd=None, timeout, env=None):
        started.set()
        await asyncio.sleep(3600)

    run.started = started
    return run


@pytest.fixture
def make(tmp_path):
    def build(runner, **raw):
        cfg = parse_config({"owner_ids": "8", "research_summary_chars": 10, **raw})
        store = Store(tmp_path / "h.db")
        notes = Notes()
        svc = ResearchService(cfg, store, tmp_path / "jobs", notes, runner=runner)
        return svc, store, notes

    return build


def test_build_argv(make, tmp_path):
    svc, _, _ = make(runner_writing("x"), research_model="gpt-r", research_effort="xhigh")
    argv = svc.build_argv(tmp_path / "j", "量子计算")
    assert argv[:6] == ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only"]
    assert argv[argv.index("-m") + 1] == "gpt-r"
    assert 'model_reasoning_effort="xhigh"' in argv
    assert 'web_search="live"' in argv
    assert argv[argv.index("-C") + 1] == str(tmp_path / "j")
    assert argv[argv.index("-o") + 1] == str(tmp_path / "j" / "report.md")
    assert "量子计算" in argv[-1]
    svc2, _, _ = make(runner_writing("x"))
    assert "-m" not in svc2.build_argv(tmp_path / "j", "t")


async def test_success(make):
    svc, store, notes = make(runner_writing("0123456789ABCDEF"))
    await svc.start()
    job = svc.submit("umo", "1", "topic")
    await notes.wait()
    await svc.stop()
    umo, text, path = notes.calls[0]
    assert umo == "umo"
    assert text == f"研究 #{job.id} 完成：topic\n\n0123456789…"
    assert Path(path).read_text(encoding="utf-8") == "0123456789ABCDEF"
    got = store.get_job(job.id)
    assert got.status == "done" and got.report_path == path and got.finished_at


@pytest.mark.parametrize(
    "runner,msg",
    [
        (runner_writing(None, rc=1, stderr="429 rate limit"), "额度"),
        (runner_writing(None, timed_out=True), "超时（1800s）"),
        (runner_writing("   "), "未生成报告"),
    ],
)
async def test_failures(make, runner, msg):
    svc, store, notes = make(runner)
    await svc.start()
    job = svc.submit("umo", "1", "t")
    await notes.wait()
    await svc.stop()
    _, text, path = notes.calls[0]
    assert text.startswith(f"研究 #{job.id} 失败：") and msg in text and path is None
    assert store.get_job(job.id).status == "failed"
    assert msg in store.get_job(job.id).error


async def test_cancel_queued_skips(make):
    runner = blocking_runner()
    svc, store, notes = make(runner)
    await svc.start()
    first = svc.submit("umo", "1", "a")
    await asyncio.wait_for(runner.started.wait(), 3)
    second = svc.submit("umo", "1", "b")
    assert svc.cancel(second.id, "1", False) == f"已取消研究 #{second.id}"
    assert store.get_job(second.id).status == "cancelled"
    assert svc.cancel(first.id, "2", False) == "只能取消自己的任务"
    assert svc.cancel(first.id, "8", True) == f"已取消研究 #{first.id}"
    await asyncio.sleep(0.05)
    assert store.get_job(first.id).status == "cancelled"
    assert svc.cancel(first.id, "1", False) == "任务已结束（cancelled）"
    assert svc.cancel(999, "1", False) == "任务不存在"
    await svc.stop()
    assert notes.calls == []


async def test_start_marks_interrupted(make):
    svc, store, notes = make(runner_writing("r"))
    j = store.create_job("umo", "1", "old", 1.0)
    await svc.start()
    await notes.wait()
    await svc.stop()
    assert notes.calls[0] == ("umo", f"研究 #{j.id} 因重启中断：old", None)
    assert store.get_job(j.id).status == "interrupted"


async def test_status_text(make):
    svc, store, _ = make(runner_writing("r"))
    assert svc.status_text("umo", None) == "本会话暂无研究任务"
    a = store.create_job("umo", "1", "alpha", 1.0)
    b = store.create_job("umo", "1", "beta", 2.0)
    store.update_job(b.id, status="failed", error="boom")
    out = svc.status_text("umo", None)
    assert out.splitlines()[0].startswith(f"#{b.id} [failed] beta")
    assert f"#{a.id} [queued] alpha" in out
    assert "boom" in svc.status_text("umo", b.id)
    assert svc.status_text("umo", 999) == "任务不存在"
    assert svc.status_text("other", a.id) == "任务不存在"
