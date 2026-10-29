"""最小 HTTP 客户端（aiohttp 由 AstrBot 提供）。"""

from __future__ import annotations


class HttpError(Exception):
    pass


class AiohttpClient:
    async def _post(self, url: str, headers: dict, payload: dict, timeout: float):
        import aiohttp

        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
        resp = await session.post(url, headers=headers, json=payload)
        if resp.status // 100 != 2:
            text = await resp.text()
            await session.close()
            raise HttpError(f"HTTP {resp.status}: {text[:200]}")
        return session, resp

    async def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict:
        session, resp = await self._post(url, headers, payload, timeout)
        try:
            return await resp.json(content_type=None)
        finally:
            await session.close()

    async def post_bytes(self, url: str, headers: dict, payload: dict, timeout: float) -> bytes:
        session, resp = await self._post(url, headers, payload, timeout)
        try:
            return await resp.read()
        finally:
            await session.close()
