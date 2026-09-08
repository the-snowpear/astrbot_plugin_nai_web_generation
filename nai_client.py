"""Nai2API Job 异步客户端。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from urllib.parse import urljoin

import aiohttp

from astrbot.api import logger

try:
    from .styles import DEFAULT_NEGATIVE, size_cost
except (ImportError, ValueError):
    from styles import DEFAULT_NEGATIVE, size_cost


class Nai2ApiError(RuntimeError):
    """Nai2API 调用失败。"""


class Nai2ApiClient:
    def __init__(
        self,
        *,
        base_url: str = "https://nai.sta1n.cn",
        token: str = "",
        model: str = "nai-diffusion-4-5-full",
        poll_interval: float = 1.0,
        max_poll_time: float = 180.0,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or "https://nai.sta1n.cn").rstrip("/")
        self.token = (token or "").strip()
        self.model = model
        self.poll_interval = max(0.3, float(poll_interval))
        self.max_poll_time = max(10.0, float(max_poll_time))
        self.timeout = max(5.0, float(timeout))
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    timeout = aiohttp.ClientTimeout(total=self.timeout, connect=15)
                    self._session = aiohttp.ClientSession(
                        timeout=timeout,
                        connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
                    )
        return self._session

    def _headers(self, with_json: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if with_json:
            headers["content-type"] = "application/json"
        if self.token:
            headers["x-user-token"] = self.token
        return headers

    def _abs_url(self, url: str | None) -> str:
        if not url:
            return ""
        s = str(url).strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
        return urljoin(self.base_url + "/", s.lstrip("/"))

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query_token: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise Nai2ApiError("未配置 API Key，请在插件配置页填写 Nai2API 密钥（STA1N-...）")

        url = path if path.startswith("http") else f"{self.base_url}{path}"
        if query_token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={self.token}"

        session = await self._session_get()
        req_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)
        try:
            async with session.request(
                method,
                url,
                headers=self._headers(with_json=body is not None),
                json=body,
                timeout=req_timeout,
            ) as resp:
                # 只能读一次 body：先 text 再 json.loads，避免 resp.json() 读空
                text = await resp.text()
                if text:
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        data = {"error": text[:300]}
                else:
                    data = {}
                if not isinstance(data, dict):
                    data = {"data": data}
                if resp.status >= 400:
                    err = data.get("error") or text[:300] or f"HTTP {resp.status}"
                    raise Nai2ApiError(str(err))
                return data
        except Nai2ApiError:
            raise
        except asyncio.TimeoutError as e:
            raise Nai2ApiError("连接 Nai2API 超时，请稍后重试") from e
        except aiohttp.ClientError as e:
            raise Nai2ApiError(f"网络错误: {e}") from e

    async def get_balance(self) -> dict[str, Any]:
        return await self._request_json("GET", "/api/me", query_token=True)

    async def submit_job(
        self,
        *,
        tag: str,
        artist: str,
        size: str = "竖图",
        steps: int = 28,
        scale: float = 6,
        cfg: float = 0,
        sampler: str = "k_dpmpp_2m_sde",
        negative: str = "",
        model: str | None = None,
        noise_schedule: str = "karras",
        cost: int | None = None,
        nocache: str = "1",
    ) -> dict[str, Any]:
        prompt = (tag or "").strip()
        if not prompt:
            raise Nai2ApiError("提示词不能为空")

        body = {
            "token": self.token,
            "tag": prompt,
            "model": model or self.model,
            "artist": artist or "",
            "size": size,
            "cost": int(cost if cost is not None else size_cost(size)),
            "steps": int(steps),
            "scale": float(scale),
            "cfg": float(cfg),
            "sampler": sampler,
            "negative": negative if negative is not None else DEFAULT_NEGATIVE,
            "nocache": str(nocache),
            "noise_schedule": noise_schedule or "karras",
        }
        logger.info(
            "[Nai2API] submit job size=%s steps=%s style_len=%s tag_preview=%s",
            size,
            steps,
            len(artist or ""),
            prompt[:80],
        )
        return await self._request_json("POST", "/api/jobs", body=body, timeout=60)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            f"/api/jobs/{job_id}",
            query_token=True,
            timeout=30,
        )

    async def poll_job(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.max_poll_time
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                job = await self.get_job(job_id)
                last_err = None
            except Nai2ApiError as e:
                # 5xx / 瞬时错误：重试
                msg = str(e).lower()
                if "http 5" in msg or "timeout" in msg or "网络" in str(e):
                    last_err = e
                    await asyncio.sleep(self.poll_interval)
                    continue
                raise

            status = str(job.get("status") or "")
            if status == "done":
                image_url = self._abs_url(job.get("imageUrl") or job.get("image_url"))
                if not image_url:
                    raise Nai2ApiError("任务完成但未返回图片地址")
                job["imageUrl"] = image_url
                return job
            if status == "failed":
                raise Nai2ApiError(str(job.get("error") or "生图任务失败"))
            await asyncio.sleep(self.poll_interval)

        if last_err:
            raise Nai2ApiError(f"轮询超时，最后错误: {last_err}")
        raise Nai2ApiError(f"生图超时（>{int(self.max_poll_time)}s）")

    async def generate(
        self,
        *,
        tag: str,
        artist: str,
        size: str = "竖图",
        steps: int = 28,
        scale: float = 6,
        cfg: float = 0,
        sampler: str = "k_dpmpp_2m_sde",
        negative: str = "",
        model: str | None = None,
        noise_schedule: str = "karras",
    ) -> dict[str, Any]:
        """提交并轮询，返回 job（含绝对 imageUrl）。"""
        job = await self.submit_job(
            tag=tag,
            artist=artist,
            size=size,
            steps=steps,
            scale=scale,
            cfg=cfg,
            sampler=sampler,
            negative=negative,
            model=model,
            noise_schedule=noise_schedule,
        )
        job_id = job.get("id") or job.get("job_id") or job.get("jobId")
        if not job_id:
            raise Nai2ApiError(f"提交成功但未返回 job id: {job}")
        return await self.poll_job(str(job_id))
