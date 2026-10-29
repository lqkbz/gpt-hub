import base64
import os
import time
from pathlib import Path

import pytest

from core.config import DrawBackendConf, parse_config
from core.draw import (
    BackendError,
    CodexCliImageBackend,
    DrawService,
    ImageResult,
    OpenAIImagesBackend,
    build_backends,
)
from core.procs import ProcResult

PNG = base64.b64encode(b"\x89PNG fake").decode()


class FakeHttp:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    async def post_json(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


def conf(**kw):
    base = dict(name="sf", type="openai_images", base_url="https://api.x/v1/", api_key="k", model="m")
    base.update(kw)
    return DrawBackendConf(**base)


async def test_openai_b64(tmp_path):
    http = FakeHttp({"data": [{"b64_json": PNG}]})
    r = await OpenAIImagesBackend(conf(), http, 30).generate("a cat", tmp_path)
    assert r.backend == "sf" and r.url is None
    assert Path(r.path).read_bytes() == b"\x89PNG fake"
    url, headers, payload, timeout = http.calls[0]
    assert url == "https://api.x/v1/images/generations"
    assert headers["Authorization"] == "Bearer k"
    assert payload == {"model": "m", "prompt": "a cat", "size": "1024x1024", "n": 1}
    assert timeout == 30


async def test_openai_url(tmp_path):
    http = FakeHttp({"data": [{"url": "https://img/1.png"}]})
    r = await OpenAIImagesBackend(conf(), http, 30).generate("x", tmp_path)
    assert r == ImageResult(url="https://img/1.png", backend="sf")


@pytest.mark.parametrize("resp", [{"data": []}, {}, {"data": [{}]}])
async def test_openai_empty(tmp_path, resp):
    with pytest.raises(BackendError):
        await OpenAIImagesBackend(conf(), FakeHttp(resp), 30).generate("x", tmp_path)


def fake_runner(write_to=None, rc=0, timed_out=False, stderr=""):
    calls = []

    async def run(argv, *, cwd=None, timeout, env=None):
        calls.append(argv)
        if write_to is not None:
            target = write_to(argv)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"img")
        return ProcResult(rc, "", stderr, timed_out)

    run.calls = calls
    return run


def out_dir_of(argv):
    return Path(argv[argv.index("-C") + 1])


async def test_codex_image_in_out_dir(tmp_path):
    runner = fake_runner(lambda argv: out_dir_of(argv) / "sub" / "cat.png")
    b = CodexCliImageBackend("sub", "codex", tmp_path / "home", 60, runner=runner)
    out = tmp_path / "out"
    out.mkdir()
    r = await b.generate("a cat", out)
    assert r.backend == "sub" and Path(r.path) == out / "sub" / "cat.png"
    argv = runner.calls[0]
    assert argv[:6] == ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "workspace-write"]
    assert "--enable" in argv and "image_generation" in argv
    assert argv[argv.index("-o") + 1] == str(out / "last.txt")
    assert "a cat" in argv[-1]


async def test_codex_image_from_codex_home(tmp_path):
    home = tmp_path / "home"
    runner = fake_runner(lambda argv: home / "generated_images" / "s1" / "ig_1.png")
    out = tmp_path / "out"
    out.mkdir()
    r = await CodexCliImageBackend("sub", "codex", home, 60, runner=runner).generate("x", out)
    assert Path(r.path).parent == out
    assert Path(r.path).read_bytes() == b"img"


async def test_codex_ignores_old_images(tmp_path):
    home = tmp_path / "home"
    old = home / "generated_images" / "old.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    past = time.time() - 3600
    os.utime(old, (past, past))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(BackendError, match="未产出图片"):
        await CodexCliImageBackend("sub", "codex", home, 60, runner=fake_runner()).generate("x", out)


@pytest.mark.parametrize(
    "kw,msg", [({"rc": 1, "stderr": "401 Unauthorized"}, "codex login"), ({"timed_out": True}, "超时")]
)
async def test_codex_failures(tmp_path, kw, msg):
    out = tmp_path / "out"
    out.mkdir()
    b = CodexCliImageBackend("sub", "codex", tmp_path / "h", 60, runner=fake_runner(**kw))
    with pytest.raises(BackendError, match=msg):
        await b.generate("x", out)


class StubBackend:
    def __init__(self, name, result=None, error=None):
        self.name, self.result, self.error = name, result, error
        self.dirs = []

    async def generate(self, prompt, out_dir):
        self.dirs.append(out_dir)
        if self.error:
            raise BackendError(self.error)
        return self.result


async def test_service_falls_back(tmp_path):
    a = StubBackend("a", error="boom")
    b = StubBackend("b", result=ImageResult(url="u", backend="b"))
    r = await DrawService([a, b], tmp_path).draw("x")
    assert r.backend == "b"
    assert a.dirs[0].is_dir() and a.dirs[0].parent == tmp_path


async def test_service_all_fail(tmp_path):
    svc = DrawService([StubBackend("a", error="e1"), StubBackend("b", error="e2")], tmp_path)
    with pytest.raises(BackendError, match="全部生图后端失败：a: e1; b: e2"):
        await svc.draw("x")


async def test_service_unexpected_error_is_wrapped(tmp_path):
    class Boom(StubBackend):
        async def generate(self, prompt, out_dir):
            raise RuntimeError("kaput")

    with pytest.raises(BackendError, match="a: kaput"):
        await DrawService([Boom("a")], tmp_path).draw("x")


async def test_service_no_backends(tmp_path):
    with pytest.raises(BackendError, match="未配置生图后端"):
        await DrawService([], tmp_path).draw("x")


def test_build_backends(tmp_path):
    cfg = parse_config(
        {"draw_backends": [{"name": "sub", "type": "codex_cli"}, {"name": "sf", "type": "openai_images"}]}
    )
    bs = build_backends(cfg, FakeHttp({}), tmp_path)
    assert [type(b).__name__ for b in bs] == ["CodexCliImageBackend", "OpenAIImagesBackend"]
    assert [b.name for b in bs] == ["sub", "sf"]
