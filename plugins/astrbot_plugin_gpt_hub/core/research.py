"""深度研究：任务队列 + codex exec（只读沙箱、联网搜索）+ 完成回传。"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

from .config import HubConfig
from .procs import Runner, classify_codex_error, run_process
from .store import ResearchJob, Store

RESEARCH_PROMPT = """你是严谨的研究员。请就下面的主题做一次深度研究。

主题：{topic}

步骤：
1. 把主题拆成 3-6 个关键子问题。
2. 针对每个子问题多轮联网搜索，阅读一手来源（官方文档、论文、权威媒体、原始数据）。
3. 交叉核对关键事实，标出存在争议或证据不足之处。
4. 用中文输出 Markdown 报告，结构：
   - # 标题
   - ## 摘要（5 行以内）
   - ## 正文（按子问题分节）
   - ## 结论与建议
   - ## 参考来源（编号列表，每条含标题与链接）
正文中的事实用 [编号] 引用来源。只输出报告本身，不要写过程说明。不要修改任何文件。"""

logger = logging.getLogger("astrbot")

Notifier = Callable[[str, str, str | None], Awaitable[None]]


class ResearchService:
    def __init__(
        self,
        cfg: HubConfig,
        store: Store,
        work_root: Path,
        notify: Notifier,
        runner: Runner = run_process,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.work_root = work_root
        self.notify = notify
        self.runner = runner
        self.clock = clock
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        for job in self.store.mark_unfinished_interrupted(self.clock()):
            await self._safe_notify(job.umo, f"研究 #{job.id} 因重启中断：{job.topic}", None)
        self._workers = [
            asyncio.create_task(self._worker()) for _ in range(self.cfg.research_concurrency)
        ]

    async def stop(self) -> None:
        tasks = [*self._workers, *self._running.values()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._workers = []
        self._running.clear()

    def submit(self, umo: str, requester: str, topic: str) -> ResearchJob:
        job = self.store.create_job(umo, requester, topic, self.clock())
        self._queue.put_nowait(job.id)
        return job

    def cancel(self, job_id: int, requester: str, is_owner: bool) -> str:
        job = self.store.get_job(job_id)
        if job is None:
            return "任务不存在"
        if job.requester != requester and not is_owner:
            return "只能取消自己的任务"
        if job.status not in ("queued", "running"):
            return f"任务已结束（{job.status}）"
        self.store.update_job(job_id, status="cancelled", finished_at=self.clock())
        task = self._running.get(job_id)
        if task is not None:
            task.cancel()
        return f"已取消研究 #{job_id}"

    def status_text(self, umo: str, job_id: int | None) -> str:
        if job_id is not None:
            job = self.store.get_job(job_id)
            if job is None or job.umo != umo:
                return "任务不存在"
            lines = [f"#{job.id} [{job.status}] {job.topic}"]
            if job.error:
                lines.append(f"错误：{job.error}")
            return "\n".join(lines)
        jobs = self.store.list_jobs(umo)
        if not jobs:
            return "本会话暂无研究任务"
        return "\n".join(f"#{j.id} [{j.status}] {j.topic}" for j in jobs)

    def build_argv(self, job_dir: Path, topic: str) -> list[str]:
        c = self.cfg
        argv = [c.codex_bin, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only"]
        if c.research_model:
            argv += ["-m", c.research_model]
        argv += ["-c", f'model_reasoning_effort="{c.research_effort}"', *c.research_extra_args]
        argv += ["-C", str(job_dir), "-o", str(job_dir / "report.md"), RESEARCH_PROMPT.format(topic=topic)]
        return argv

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            job = self.store.get_job(job_id)
            if job is None or job.status != "queued":
                continue
            task = asyncio.create_task(self._run_job(job))
            self._running[job_id] = task
            try:
                await asyncio.wait({task})
            finally:
                self._running.pop(job_id, None)

    async def _run_job(self, job: ResearchJob) -> None:
        job_dir = self.work_root / f"job-{job.id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        self.store.update_job(job.id, status="running")
        try:
            r = await self.runner(
                self.build_argv(job_dir, job.topic),
                cwd=str(job_dir),
                timeout=self.cfg.research_timeout,
            )
        except asyncio.CancelledError:
            return  # 状态由 cancel() 设置；stop() 时保持 running，重启后标记中断
        except Exception as e:  # noqa: BLE001
            logger.exception("gpt_hub 研究任务 #%s 启动失败", job.id)
            await self._fail(job, f"启动 codex 失败：{e}")
            return

        report = job_dir / "report.md"
        if r.timed_out:
            await self._fail(job, f"超时（{self.cfg.research_timeout}s）")
        elif r.returncode != 0:
            await self._fail(job, classify_codex_error(r.stderr))
        elif not report.is_file() or not report.read_text(encoding="utf-8").strip():
            await self._fail(job, "未生成报告")
        else:
            text = report.read_text(encoding="utf-8").strip()
            n = self.cfg.research_summary_chars
            summary = text[:n] + ("…" if len(text) > n else "")
            self.store.update_job(
                job.id, status="done", finished_at=self.clock(), report_path=str(report)
            )
            await self._safe_notify(job.umo, f"研究 #{job.id} 完成：{job.topic}\n\n{summary}", str(report))

    async def _fail(self, job: ResearchJob, error: str) -> None:
        self.store.update_job(job.id, status="failed", finished_at=self.clock(), error=error)
        await self._safe_notify(job.umo, f"研究 #{job.id} 失败：{error}", None)

    async def _safe_notify(self, umo: str, text: str, file_path: str | None) -> None:
        try:
            await self.notify(umo, text, file_path)
        except Exception:  # noqa: BLE001 - 通知失败不影响任务状态
            logger.exception("gpt_hub 研究结果通知失败 umo=%s", umo)
