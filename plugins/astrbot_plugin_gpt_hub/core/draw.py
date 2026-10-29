"""生图：后端接口、OpenAI 兼容 API 后端、Codex CLI（订阅）后端、按序回落。"""

from __future__ import annotations

import base64
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import DrawBackendConf, HubConfig
from .procs import Runner, classify_codex_error, run_process

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

CODEX_DRAW_PROMPT = (
    "使用你的图像生成工具，根据下面的描述生成一张图片，"
    "并把最终图片文件保存到当前工作目录。不要做其他事情。\n\n描述：{prompt}"
)


class BackendError(Exception):
    pass


@dataclass
class ImageResult:
    path: str | None = None
    url: str | None = None
    backend: str = ""


class ImageBackend(Protocol):
    name: str

    async def generate(self, prompt: str, out_dir: Path) -> ImageResult: ...


class HttpClient(Protocol):
    async def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict: ...


class AiohttpClient:
    async def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict:
        import aiohttp

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.post(url, headers=headers, json=payload) as resp:
                if resp.status // 100 != 2:
                    raise BackendError(f"HTTP {resp.status}: {(await resp.text())[:200]}")
                return await resp.json(content_type=None)


class OpenAIImagesBackend:
    def __init__(self, conf: DrawBackendConf, http: HttpClient, timeout: float) -> None:
        self.name = conf.name
        self.conf = conf
        self.http = http
        self.timeout = timeout

    async def generate(self, prompt: str, out_dir: Path) -> ImageResult:
        c = self.conf
        resp = await self.http.post_json(
            f"{c.base_url.rstrip('/')}/images/generations",
            {"Authorization": f"Bearer {c.api_key}", "Content-Type": "application/json"},
            {"model": c.model, "prompt": prompt, "size": c.size, "n": 1},
            self.timeout,
        )
        data = (resp or {}).get("data") or []
        item = data[0] if data else {}
        if item.get("b64_json"):
            path = out_dir / f"{self.name}.png"
            path.write_bytes(base64.b64decode(item["b64_json"]))
            return ImageResult(path=str(path), backend=self.name)
        if item.get("url"):
            return ImageResult(url=item["url"], backend=self.name)
        raise BackendError("接口未返回图片")


def _newest_image(roots: list[Path], since: float) -> Path | None:
    found = [
        p
        for root in roots
        if root.is_dir()
        for p in root.rglob("*")
        if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file() and p.stat().st_mtime >= since
    ]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


class CodexCliImageBackend:
    def __init__(
        self,
        name: str,
        codex_bin: str,
        codex_home: Path,
        timeout: float,
        runner: Runner = run_process,
        clock=time.time,
    ) -> None:
        self.name = name
        self.codex_bin = codex_bin
        self.codex_home = codex_home
        self.timeout = timeout
        self.runner = runner
        self.clock = clock

    async def generate(self, prompt: str, out_dir: Path) -> ImageResult:
        argv = [
            self.codex_bin, "exec", "--skip-git-repo-check", "--ephemeral",
            "-s", "workspace-write", "--enable", "image_generation",
            "-C", str(out_dir), "-o", str(out_dir / "last.txt"),
            CODEX_DRAW_PROMPT.format(prompt=prompt),
        ]  # fmt: skip
        start = self.clock() - 1
        r = await self.runner(argv, cwd=str(out_dir), timeout=self.timeout)
        if r.timed_out:
            raise BackendError(f"超时（{self.timeout:g}s）")
        if r.returncode != 0:
            raise BackendError(classify_codex_error(r.stderr))
        img = _newest_image([out_dir, self.codex_home / "generated_images"], start)
        if img is None:
            raise BackendError("codex 未产出图片")
        if out_dir not in img.parents:
            dest = out_dir / img.name
            shutil.copy2(img, dest)
            img = dest
        return ImageResult(path=str(img), backend=self.name)


class DrawService:
    def __init__(self, backends: list[ImageBackend], work_root: Path) -> None:
        self.backends = backends
        self.work_root = work_root

    async def draw(self, prompt: str) -> ImageResult:
        if not self.backends:
            raise BackendError("未配置生图后端")
        out_dir = self.work_root / uuid.uuid4().hex
        out_dir.mkdir(parents=True, exist_ok=True)
        errors = []
        for b in self.backends:
            try:
                return await b.generate(prompt, out_dir)
            except Exception as e:  # noqa: BLE001 - 任一后端失败都换下一个
                errors.append(f"{b.name}: {e}")
        raise BackendError("全部生图后端失败：" + "; ".join(errors))


def build_backends(
    cfg: HubConfig, http: HttpClient, codex_home: Path, runner: Runner = run_process
) -> list[ImageBackend]:
    out: list[ImageBackend] = []
    for c in cfg.draw_backends:
        if c.type == "codex_cli":
            out.append(CodexCliImageBackend(c.name, cfg.codex_bin, codex_home, cfg.draw_timeout, runner))
        else:
            out.append(OpenAIImagesBackend(c, http, cfg.draw_timeout))
    return out
