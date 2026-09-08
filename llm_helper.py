"""LLM 调用：独立 OpenAI 兼容接口优先，否则回退 AstrBot Provider。"""

from __future__ import annotations

import json
import re
from typing import Any

import aiohttp

from astrbot.api import logger


class LlmError(RuntimeError):
    pass


def _repair_newlines_in_json_strings(s: str) -> str:
    """把 JSON 字符串字面量里的裸换行转义为 \\n，兼容模型输出。"""
    out: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
            elif ch == "\\":
                out.append(ch)
                escape = True
            elif ch == '"':
                out.append(ch)
                in_str = False
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                continue
            elif ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_str = True
    return "".join(out)


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出中尽量解析出 JSON 对象。"""
    if not text:
        raise LlmError("LLM 返回为空")

    raw = text.strip()

    # ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    candidates = [raw]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])

    for cand in candidates:
        for variant in (cand, _repair_newlines_in_json_strings(cand)):
            try:
                data = json.loads(variant)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue

    raise LlmError(f"无法解析 LLM JSON 输出: {text[:200]}")


class LlmHelper:
    def __init__(
        self,
        *,
        context: Any,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        provider_id: str = "",
        temperature: float = 0.2,
        timeout: float = 90.0,
    ):
        self.context = context
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.provider_id = (provider_id or "").strip()
        self.temperature = float(temperature)
        self.timeout = float(timeout)
        self._session: aiohttp.ClientSession | None = None

    def has_config(self) -> bool:
        if self.base_url and self.api_key and self.model:
            return True
        if self.provider_id:
            return True
        # 尝试默认 provider 是否存在
        try:
            if self.context and hasattr(self.context, "get_using_provider"):
                return self.context.get_using_provider() is not None
        except Exception:
            pass
        return False

    def describe_backend(self) -> str:
        if self.base_url and self.api_key and self.model:
            return f"openai-compat:{self.model}"
        if self.provider_id:
            return f"astrbot-provider:{self.provider_id}"
        return "astrbot-default-provider"

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> str:
        temp = self.temperature if temperature is None else temperature
        if self.base_url and self.api_key and self.model:
            return await self._chat_openai(system=system, user=user, temperature=temp)
        return await self._chat_astrbot(system=system, user=user, temperature=temp)

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        text = await self.chat(system=system, user=user, temperature=temperature)
        return extract_json_object(text)

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout, connect=20)
            )
        return self._session

    async def _chat_openai(self, *, system: str, user: str, temperature: float) -> str:
        url = self.base_url
        if not url.endswith("/chat/completions"):
            # 兼容 .../v1 与 .../v1/chat/completions
            if url.endswith("/v1"):
                url = url + "/chat/completions"
            elif "/chat/completions" not in url:
                url = url.rstrip("/") + "/v1/chat/completions"

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }
        session = await self._session_get()
        try:
            async with session.post(url, headers=headers, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise LlmError(f"LLM HTTP {resp.status}: {text[:300]}")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    raise LlmError(f"LLM 返回非 JSON: {text[:200]}") from e
                choices = data.get("choices") or []
                if not choices:
                    raise LlmError(f"LLM 无 choices: {text[:200]}")
                msg = choices[0].get("message") or {}
                content = msg.get("content") or ""
                if isinstance(content, list):
                    # 部分兼容接口 content 为分段
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                if not str(content).strip():
                    raise LlmError("LLM 返回 content 为空")
                return str(content)
        except LlmError:
            raise
        except Exception as e:
            raise LlmError(f"独立 LLM 调用失败: {e}") from e

    async def _chat_astrbot(self, *, system: str, user: str, temperature: float) -> str:
        if not self.context:
            raise LlmError("AstrBot context 不可用，且未配置独立 LLM")

        provider = None
        try:
            if self.provider_id and hasattr(self.context, "get_provider_by_id"):
                provider = self.context.get_provider_by_id(self.provider_id)
            if provider is None and hasattr(self.context, "get_using_provider"):
                provider = self.context.get_using_provider()
        except Exception as e:
            logger.warning("[NaiPlugin] 获取 provider 失败: %s", e)

        if provider is None:
            raise LlmError(
                "未配置 LLM。请在插件配置填写独立 OpenAI 兼容接口，"
                "或选择 AstrBot Provider（llm_provider）"
            )

        # 兼容不同 AstrBot 版本的 text_chat 签名
        try:
            result = await provider.text_chat(
                prompt=user.strip(),
                session_id=None,
                contexts=[],
                image_urls=[],
                func_tool=None,
                system_prompt=system,
            )
        except TypeError:
            # Older providers may not support ``system_prompt``. Only those
            # fallbacks receive a combined prompt; supported providers must
            # not see the system instruction twice.
            prompt = f"{system.strip()}\n\n---\n\n用户输入：\n{user.strip()}"
            try:
                result = await provider.text_chat(prompt=prompt)
            except TypeError:
                result = await provider.text_chat(prompt)

        text = self._coerce_provider_result(result)
        if not text.strip():
            raise LlmError("AstrBot Provider 返回为空")
        return text

    @staticmethod
    def _coerce_provider_result(result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        # LLMResponse 常见属性
        for attr in ("completion_text", "result_chain", "text", "content"):
            if hasattr(result, attr):
                val = getattr(result, attr)
                if isinstance(val, str) and val.strip():
                    return val
                # MessageChain
                if val is not None and hasattr(val, "get_plain_text"):
                    try:
                        return val.get_plain_text() or ""
                    except Exception:
                        pass
        if isinstance(result, dict):
            for k in ("completion_text", "content", "text", "message"):
                if k in result and result[k]:
                    return str(result[k])
        return str(result)
