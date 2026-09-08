"""AstrBot NAI 生图插件。

指令：
  /nai   使用默认参数直接生图（可覆盖 style/size 等）
  /nai2  LLM 提取参数 + 中文直译为 tag（不创意改写）
  /nai3  LLM 按引导文件创作完整提示词并生图
"""

import re
import time
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:
    from astrbot.core.star.filter.command import GreedyStr
except Exception:  # pragma: no cover
    GreedyStr = str  # type: ignore

try:
    from .llm_helper import LlmError, LlmHelper, extract_json_object
    from .nai_client import Nai2ApiClient, Nai2ApiError
    from .styles import (
        DEFAULT_NEGATIVE,
        VALID_SAMPLERS,
        get_artist,
        list_styles,
        merge_gen_params,
        normalize_size,
        resolve_style_id,
        styles_help_text,
    )
except (ImportError, ValueError):
    from llm_helper import LlmError, LlmHelper, extract_json_object
    from nai_client import Nai2ApiClient, Nai2ApiError
    from styles import (
        DEFAULT_NEGATIVE,
        VALID_SAMPLERS,
        get_artist,
        list_styles,
        merge_gen_params,
        normalize_size,
        resolve_style_id,
        styles_help_text,
    )


def _cmd_args(event: AstrMessageEvent, greedy: str | None, cmd_name: str) -> str:
    """提取完整指令参数，优先使用未被命令解析器拆分的原始消息。"""
    raw = ""
    if hasattr(event, "get_message_str"):
        raw = event.get_message_str() or ""
    if not raw:
        raw = getattr(event, "message_str", None) or ""
    raw = str(raw).strip()
    match = re.match(
        rf"^[/!！．。]?\s*{re.escape(cmd_name)}(?=\s|$)",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        # Keep all internal whitespace intact: NAI tag weighting and natural
        # language prompts may intentionally contain repeated spaces.
        return raw[match.end() :].strip()
    if greedy is not None and str(greedy).strip():
        return str(greedy).strip()
    return raw

PLUGIN_DIR = Path(__file__).resolve().parent

_SIZE_PREFIX = re.compile(
    r"^(2K竖图|2K横图|2K方图|4K竖图|4K横图|4K方图|竖图|横图|方图)\s+",
    re.IGNORECASE,
)
_FLAG_STYLE = re.compile(r"--style\s+(\S+)", re.IGNORECASE)
_FLAG_SAMPLER = re.compile(r"--sampler\s+(\S+)", re.IGNORECASE)
_FLAG_STEPS = re.compile(r"--steps\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_FLAG_SCALE = re.compile(r"--scale\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_FLAG_CFG = re.compile(r"--cfg\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_FLAG_NEGATIVE = re.compile(
    r"--negative\s+(.+?)(?=\s+--(?:style|sampler|steps|scale|cfg)\s+|$)",
    re.IGNORECASE | re.DOTALL,
)


def _load_prompt(name: str) -> str:
    path = PLUGIN_DIR / "prompts" / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _cfg_get(config: dict, key: str, default: Any = None) -> Any:
    if config is None:
        return default
    try:
        if key in config:
            return config[key]
    except Exception:
        pass
    if hasattr(config, "get"):
        return config.get(key, default)
    return default


def parse_nai_args(text: str) -> dict[str, Any]:
    """解析 /nai 参数。"""
    text = (text or "").strip()
    size = None
    m = _SIZE_PREFIX.match(text)
    if m:
        size = m.group(1)
        text = text[m.end() :]

    def _take(pattern: re.Pattern[str]) -> str | None:
        nonlocal text
        mm = pattern.search(text)
        if not mm:
            return None
        val = mm.group(1).strip()
        text = (text[: mm.start()] + text[mm.end() :]).strip()
        return val

    style = _take(_FLAG_STYLE)
    sampler = _take(_FLAG_SAMPLER)
    steps_s = _take(_FLAG_STEPS)
    scale_s = _take(_FLAG_SCALE)
    cfg_s = _take(_FLAG_CFG)
    negative = _take(_FLAG_NEGATIVE)

    return {
        "size": size,
        "style": style,
        "sampler": sampler,
        "steps": int(float(steps_s)) if steps_s else None,
        "scale": float(scale_s) if scale_s else None,
        "cfg": float(cfg_s) if cfg_s else None,
        "negative": negative,
        "prompt": text.strip(),
    }


class Main(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.client = self._build_client()
        self.llm = self._build_llm()
        self._nai2_system = _load_prompt("nai2_system.txt")
        self._nai3_system = _load_prompt("nai3_system.txt")

    def _build_client(self) -> Nai2ApiClient:
        c = self.config
        return Nai2ApiClient(
            base_url=str(_cfg_get(c, "base_url", "https://nai.sta1n.cn")),
            token=str(_cfg_get(c, "api_key", "")),
            model=str(_cfg_get(c, "model", "nai-diffusion-4-5-full")),
            poll_interval=float(_cfg_get(c, "poll_interval", 1.0)),
            max_poll_time=float(_cfg_get(c, "max_poll_time", 180)),
        )

    def _build_llm(self) -> LlmHelper:
        c = self.config
        return LlmHelper(
            context=self.context,
            base_url=str(_cfg_get(c, "llm_base_url", "")),
            api_key=str(_cfg_get(c, "llm_api_key", "")),
            model=str(_cfg_get(c, "llm_model", "")),
            provider_id=str(_cfg_get(c, "llm_provider", "")),
            temperature=float(_cfg_get(c, "llm_temperature", 0.2)),
        )

    def _reload_runtime(self) -> None:
        """同步最新配置到 client（不重建 LLM session，避免泄漏）。"""
        self.client.token = str(_cfg_get(self.config, "api_key", "")).strip()
        self.client.base_url = str(
            _cfg_get(self.config, "base_url", "https://nai.sta1n.cn")
        ).rstrip("/")
        self.client.model = str(
            _cfg_get(self.config, "model", "nai-diffusion-4-5-full")
        )
        self.client.poll_interval = float(_cfg_get(self.config, "poll_interval", 1.0))
        self.client.max_poll_time = float(_cfg_get(self.config, "max_poll_time", 180))
        # 仅更新 LLM 配置字段，保留已有 aiohttp session
        self.llm.base_url = str(_cfg_get(self.config, "llm_base_url", "")).rstrip("/")
        self.llm.api_key = str(_cfg_get(self.config, "llm_api_key", "")).strip()
        self.llm.model = str(_cfg_get(self.config, "llm_model", "")).strip()
        self.llm.provider_id = str(_cfg_get(self.config, "llm_provider", "")).strip()
        self.llm.temperature = float(_cfg_get(self.config, "llm_temperature", 0.2))

    @property
    def style_pack(self) -> str:
        pack = str(_cfg_get(self.config, "style_pack", "doc712")).strip()
        return pack if pack in ("doc712", "website") else "doc712"

    def _is_compact_mode(self) -> bool:
        return str(_cfg_get(self.config, "message_mode", "verbose")).strip().lower() == "compact"

    def _compact_start_message(self, command: str) -> str:
        return f"⏳ /{command} 已开始任务，正在生成…"

    def _is_onebot_v11_group(self, event: AstrMessageEvent) -> bool:
        """只在可明确识别的 OneBot v11 群聊中发送合并转发。"""
        platform_name = ""
        get_platform_name = getattr(event, "get_platform_name", None)
        if callable(get_platform_name):
            try:
                platform_name = str(get_platform_name() or "")
            except Exception:
                pass
        if not platform_name:
            platform_name = str(getattr(event, "platform_name", "") or "")
        if not platform_name:
            origin = str(getattr(event, "unified_msg_origin", "") or "")
            platform_name = origin.split(":", 1)[0]

        normalized = platform_name.lower()
        if not any(name in normalized for name in ("onebot", "aiocqhttp", "napcat", "lagrange")):
            return False

        get_group_id = getattr(event, "get_group_id", None)
        if not callable(get_group_id):
            return False
        try:
            return bool(get_group_id())
        except Exception:
            return False

    def _format_generation_details(
        self,
        command: str,
        raw_input: str,
        params: dict[str, Any],
        elapsed: float,
    ) -> str:
        """生成紧凑模式的完整详情；仅使用生图参数，避免泄露配置密钥。"""
        return (
            f"✅ /{command} 生成详情\n\n"
            f"原始输入:\n{raw_input}\n\n"
            f"最终正向提示词:\n{params.get('tag') or ''}\n\n"
            f"最终负向提示词:\n{params.get('negative') or ''}\n\n"
            "实际生效参数:\n"
            f"style={params.get('style')}\n"
            f"artist={params.get('artist') or 'none'}\n"
            f"model={params.get('model')}\n"
            f"size={params.get('size')}\n"
            f"steps={params.get('steps')}\n"
            f"scale={params.get('scale')}\n"
            f"cfg={params.get('cfg')}\n"
            f"sampler={params.get('sampler')}\n"
            f"noise_schedule={params.get('noise_schedule')}\n"
            f"耗时={elapsed:.1f}s"
        )

    def _compact_details_result(self, event: AstrMessageEvent, details: str):
        """OneBot v11 群聊使用合并转发；其余平台安全降级为普通消息。"""
        if self._is_onebot_v11_group(event):
            try:
                from astrbot.api.message_components import Node, Plain

                sender_id = str(getattr(event, "get_sender_id", lambda: "")() or "")
                sender = getattr(getattr(event, "message_obj", None), "sender", None)
                name = str(getattr(sender, "nickname", "") or "NAI 生图详情")
                node = Node(
                    uin=int(sender_id) if sender_id.isdigit() else 0,
                    name=name,
                    content=[Plain(details)],
                )
                return event.chain_result([node])
            except Exception as e:
                logger.warning("[NaiPlugin] 合并转发不可用，降级普通详情: %s", e)
        return event.plain_result(details)

    def _default_gen_base(self) -> dict[str, Any]:
        c = self.config
        # The configured default is intentional user preference. ``none`` is
        # the safe default and produces an empty Nai2API artist prefix.
        default_style = str(_cfg_get(c, "default_style", "none"))
        sid, artist = get_artist(self.style_pack, default_style)
        size = normalize_size(
            str(_cfg_get(c, "default_size", "竖图")),
            default="竖图",
            allow_2k=bool(_cfg_get(c, "allow_2k", True)),
            allow_4k=bool(_cfg_get(c, "allow_4k", True)),
        )
        negative = str(_cfg_get(c, "negative", "") or DEFAULT_NEGATIVE)
        return {
            "style": sid,
            "artist": artist,
            "size": size,
            "steps": int(_cfg_get(c, "steps", 28)),
            "scale": float(_cfg_get(c, "scale", 6)),
            "cfg": float(_cfg_get(c, "cfg", 0)),
            "sampler": str(_cfg_get(c, "sampler", "k_dpmpp_2m_sde")),
            "noise_schedule": str(_cfg_get(c, "noise_schedule", "karras")),
            "negative": negative,
            "model": str(_cfg_get(c, "model", "nai-diffusion-4-5-full")),
        }

    def _apply_style(self, params: dict[str, Any], style_id: str | None) -> dict[str, Any]:
        if style_id is None:
            style_id = params.get("style")
        elif str(style_id).strip().lower() == "default":
            style_id = str(_cfg_get(self.config, "default_style", "none"))
        sid, artist = get_artist(self.style_pack, style_id)
        params["style"] = sid
        params["artist"] = artist
        return params

    def _apply_size(self, params: dict[str, Any], size: str | None) -> dict[str, Any]:
        params["size"] = normalize_size(
            size or params.get("size"),
            default=str(_cfg_get(self.config, "default_size", "竖图")),
            allow_2k=bool(_cfg_get(self.config, "allow_2k", True)),
            allow_4k=bool(_cfg_get(self.config, "allow_4k", True)),
        )
        return params

    def _sanitize_sampler(self, sampler: str | None, fallback: str) -> str:
        if sampler and sampler in VALID_SAMPLERS:
            return sampler
        if fallback in VALID_SAMPLERS:
            return fallback
        return "k_dpmpp_2m_sde"

    def _params_for_llm_tool(
        self,
        prompt: str,
        negative_prompt: str,
        style: str,
        size: str,
    ) -> dict[str, Any]:
        """将主 LLM 给出的工具参数合并到配置页默认生图参数。"""
        params = self._default_gen_base()
        requested_style = str(style or "default").strip()
        style_key = requested_style.lower()
        if style_key in ("none", "off", "无", "无画风"):
            requested_style = "none"
        elif style_key != "default" and resolve_style_id(
            self.style_pack, requested_style
        ) is None:
            logger.warning(
                "[NaiPlugin] LLM 工具返回未知 style，已禁用画风注入: %s",
                requested_style,
            )
            requested_style = "none"

        params = self._apply_style(params, requested_style)
        params = self._apply_size(params, str(size or "").strip() or None)
        params["sampler"] = self._sanitize_sampler(
            params.get("sampler"), str(params.get("sampler") or "")
        )
        if str(negative_prompt or "").strip():
            params["negative"] = str(negative_prompt).strip()
        params["tag"] = str(prompt).strip()
        return params

    async def _generate_job(self, params: dict[str, Any]) -> dict[str, Any]:
        """调用 Nai2API；调用方自行决定如何向用户呈现结果。"""
        return await self.client.generate(
            tag=params["tag"],
            artist=params["artist"],
            size=params["size"],
            steps=int(params["steps"]),
            scale=float(params["scale"]),
            cfg=float(params["cfg"]),
            sampler=params["sampler"],
            negative=params.get("negative") or "",
            model=params.get("model"),
            noise_schedule=params.get("noise_schedule") or "karras",
        )

    @staticmethod
    def _llm_tool_failure(reason: str) -> str:
        return (
            f"NAI 绘图失败：{reason}。请不要在本轮再次调用生图工具；"
            "请按照当前人格语气简短告诉用户绘图失败。不要输出工具参数、"
            "系统日志、API Key、认证信息或内部异常。"
        )

    def _help_text(self) -> str:
        return (
            "NAI 生图插件\n"
            "—— /nai [尺寸] <提示词> [--style ID] [--negative ..] [--steps N] [--scale N] [--cfg N] [--sampler NAME]\n"
            "—— /nai 余额 | balance\n"
            "—— /nai 画风 | styles\n"
            "—— /nai2 <任意描述>  LLM 提取参数，中文直译为 tag（不扩写）\n"
            "—— /nai3 <任意描述>  LLM 创作完整提示词并生图\n"
            "示例:\n"
            "  /nai 1girl, silver hair, looking at viewer --style galgame\n"
            "  /nai 2K竖图 1girl, school uniform --style fresh\n"
            "  /nai2 帮我画一张竖图银发少女，galgame 风\n"
            "  /nai3 雨夜霓虹下撑透明伞的银发女孩\n"
        )

    async def terminate(self):
        try:
            await self.client.close()
        except Exception:
            pass
        try:
            await self.llm.close()
        except Exception:
            pass

    # ---------------- LLM tool ----------------

    @filter.llm_tool(name="nai_generate_image")
    async def nai_generate_image(
        self,
        event: AstrMessageEvent,
        prompt: str = "",
        negative_prompt: str = "",
        style: str = "default",
        size: str = "",
    ):
        """当用户明确要求绘制或生成一张新图片时，用 NovelAI 生成一张图片。不要因为讨论图片、分析已有图片或随口提到画面而调用。你必须直接编写忠实于用户要求的完整英文 NovelAI 标签提示词，保留人物数量、身份、动作、视角、构图、场景、光照、情绪和画幅约束；不要擅自添加固定角色、画师、画风或无关元素。每轮默认只调用一次。未指定画风时使用 default；明确要求无预设画风时使用 none。根据构图选择普通竖图、横图或方图；只有用户明确要求高分辨率时才能选择 2K 或 4K。

        Args:
            prompt(string): 完整英文 NovelAI 正向提示词，使用逗号分隔的标签，忠实覆盖用户要求并保留必要的连续空格。
            negative_prompt(string): 用户明确要求的英文负向提示词；没有特殊要求时必须传空字符串以使用配置页默认值。
            style(string): 画风 ID。未指定传 default；无预设画风传 none；也可传 fresh、comicDoujin、2.5d、lolita25d、doujin、galgame、animeOld、realistic_loli。
            size(string): 竖图、横图、方图、2K竖图、2K横图、2K方图、4K竖图、4K横图或4K方图。
        """
        if not bool(_cfg_get(self.config, "enable_llm_tool", True)):
            yield self._llm_tool_failure("管理员已关闭自动生图工具")
            return

        try:
            self._reload_runtime()
        except Exception:
            logger.exception("[NaiPlugin] LLM 工具加载配置失败")
            yield self._llm_tool_failure("生图配置无效")
            return

        final_prompt = str(prompt or "").strip()
        if not final_prompt:
            yield self._llm_tool_failure("没有获得有效的绘图提示词")
            return

        if not str(_cfg_get(self.config, "api_key", "")).strip() and not self.client.token:
            yield self._llm_tool_failure("生图服务尚未配置")
            return

        try:
            params = self._params_for_llm_tool(
                final_prompt,
                negative_prompt,
                style,
                size,
            )
            job = await self._generate_job(params)
        except Nai2ApiError as e:
            logger.warning("[NaiPlugin] LLM 工具生图失败: %s", e)
            yield self._llm_tool_failure("绘图服务暂时不可用")
            return
        except Exception:
            logger.exception("[NaiPlugin] LLM tool generate error")
            yield self._llm_tool_failure("绘图服务发生内部错误")
            return

        image_url = (job.get("imageUrl") or "") if isinstance(job, dict) else ""
        if not image_url:
            logger.warning("[NaiPlugin] LLM 工具生图完成但没有图片 URL")
            yield self._llm_tool_failure("绘图服务没有返回图片")
            return

        # AstrBot 4.23.6 会把工具中的 MessageEventResult 直接发给用户并结束
        # Agent Loop，因此成功路径只会出现图片，不会再追加人格文本或进度消息。
        yield event.image_result(image_url)

    # ---------------- commands ----------------

    @filter.command("nai")
    async def cmd_nai(self, event: AstrMessageEvent, args: GreedyStr):
        """直接生图 / 查余额 / 列画风"""
        self._reload_runtime()
        raw = _cmd_args(event, args, "nai")

        if not raw:
            yield event.plain_result(self._help_text())
            return

        low = raw.lower()
        if raw in ("余额", "点数", "次数") or low in ("balance", "quota"):
            async for r in self._handle_balance(event):
                yield r
            return

        if raw in ("画风", "风格", "预设") or low in ("styles", "style", "presets"):
            yield event.plain_result(styles_help_text(self.style_pack))
            return

        if raw in ("help", "帮助", "?"):
            yield event.plain_result(self._help_text())
            return

        parsed = parse_nai_args(raw)
        prompt = parsed["prompt"]
        if not prompt:
            yield event.plain_result("提示词不能为空。\n" + self._help_text())
            return
        requested_style = parsed["style"]
        if (
            requested_style
            and requested_style.strip().lower() != "default"
            and resolve_style_id(self.style_pack, requested_style) is None
        ):
            yield event.plain_result(
                f"未知画风 ID: {requested_style}。使用 /nai 画风 查看可用画风；"
                "不附加预设可使用 --style none。"
            )
            return

        base = self._default_gen_base()
        params = merge_gen_params(
            base,
            {
                "steps": parsed["steps"],
                "scale": parsed["scale"],
                "cfg": parsed["cfg"],
                "sampler": parsed["sampler"],
                "negative": parsed["negative"],
            },
        )
        params = self._apply_style(params, parsed["style"])
        params = self._apply_size(params, parsed["size"])
        params["sampler"] = self._sanitize_sampler(params.get("sampler"), base["sampler"])
        params["tag"] = prompt

        async for r in self._run_generate(
            event, params, command="nai", raw_input=raw, header=None
        ):
            yield r

    @filter.command("nai2")
    async def cmd_nai2(self, event: AstrMessageEvent, args: GreedyStr):
        """LLM 提取参数 + 直译，不改写创意"""
        self._reload_runtime()
        raw = _cmd_args(event, args, "nai2")
        if not raw:
            yield event.plain_result(
                "用法: /nai2 <描述>\n"
                "会用 LLM 提取 style/size 等参数；中文画面描述直译为英文 tag，不做创意扩写。"
            )
            return

        if not self.llm.has_config():
            yield event.plain_result(
                "未配置 LLM。请在插件配置填写独立 OpenAI 兼容接口，或选择 AstrBot Provider。"
            )
            return

        compact = self._is_compact_mode()
        if compact:
            yield event.plain_result(self._compact_start_message("nai2"))
        elif bool(_cfg_get(self.config, "show_progress", True)):
            yield event.plain_result("🧠 正在用 LLM 提取参数…")

        styles = list_styles(self.style_pack)
        style_lines = ", ".join(f"{sid}({label})" for sid, label in styles)
        user_msg = (
            f"当前画风包: {self.style_pack}\n"
            f"可选 style: {style_lines}\n"
            f"可选 size: 竖图/横图/方图/2K竖图/2K横图/2K方图/4K竖图/4K横图/4K方图\n"
            f"可选 sampler: {', '.join(sorted(VALID_SAMPLERS))}\n\n"
            f"用户输入:\n{raw}"
        )

        try:
            data = await self.llm.chat_json(
                system=self._nai2_system or "Extract NAI params as JSON.",
                user=user_msg,
                temperature=float(_cfg_get(self.config, "llm_temperature", 0.2)),
            )
        except (LlmError, Exception) as e:
            logger.warning("[NaiPlugin] nai2 LLM 失败，回退原文: %s", e)
            data = {
                "tag": raw,
                "style": None,
                "size": None,
                "steps": None,
                "scale": None,
                "cfg": None,
                "sampler": None,
                "negative": None,
                "notes": f"LLM 失败回退: {e}",
            }

        params = self._params_from_llm_json(data, fallback_tag=raw)
        header = None
        if not compact and bool(_cfg_get(self.config, "show_params", True)):
            header = (
                f"📋 /nai2 参数\n"
                f"style={params['style']} size={params['size']} "
                f"steps={params['steps']} scale={params['scale']}\n"
                f"tag: {params['tag'][:180]}{'…' if len(params['tag']) > 180 else ''}"
            )

        async for r in self._run_generate(
            event,
            params,
            command="nai2",
            raw_input=raw,
            header=header,
            compact_start_sent=compact,
        ):
            yield r

    @filter.command("nai3")
    async def cmd_nai3(self, event: AstrMessageEvent, args: GreedyStr):
        """LLM 创作完整提示词并生图（Anima 双段引导）"""
        self._reload_runtime()
        raw = _cmd_args(event, args, "nai3")
        if not raw:
            yield event.plain_result(
                "用法: /nai3 <任意描述>\n"
                "LLM 会按 Anima 引导撰写「严格 tag 行 + 空间描述段落」并选定参数后生图。"
            )
            return

        if not self.llm.has_config():
            yield event.plain_result(
                "未配置 LLM。请在插件配置填写独立 OpenAI 兼容接口，或选择 AstrBot Provider。"
            )
            return

        compact = self._is_compact_mode()
        if compact:
            yield event.plain_result(self._compact_start_message("nai3"))
        elif bool(_cfg_get(self.config, "show_progress", True)):
            yield event.plain_result("🎨 正在用 LLM 创作 Anima 提示词…")

        styles = list_styles(self.style_pack)
        style_lines = ", ".join(f"{sid}({label})" for sid, label in styles)
        user_msg = (
            f"当前画风包: {self.style_pack}\n"
            f"可选 style ID 列表: {style_lines}\n"
            f"可选 size: 竖图/横图/方图/2K竖图/2K横图/2K方图/4K竖图/4K横图/4K方图\n"
            f"可选 sampler: {', '.join(sorted(VALID_SAMPLERS))}\n\n"
            f"用户需求:\n{raw}"
        )

        temp = min(1.2, float(_cfg_get(self.config, "llm_temperature", 0.2)) + 0.5)
        try:
            text = await self.llm.chat(
                system=self._nai3_system or "Write NAI prompts as JSON.",
                user=user_msg,
                temperature=temp,
            )
            data = self._parse_nai3_llm_output(text)
        except (LlmError, Exception) as e:
            logger.error("[NaiPlugin] nai3 LLM 失败: %s", e)
            yield event.plain_result(f"LLM 创作失败: {e}")
            return

        tag = str(data.get("tag") or "").strip()
        if not tag:
            yield event.plain_result("LLM 未返回 tag，请重试。")
            return

        # 若未给 size，从 caption 画幅词推断
        if not data.get("size"):
            inferred = self._infer_size_from_tag(tag)
            if inferred:
                data["size"] = inferred

        params = self._params_from_llm_json(data, fallback_tag=tag)
        header = None
        if not compact and bool(_cfg_get(self.config, "show_params", True)):
            notes = str(data.get("notes") or "").strip()
            header = (
                f"📋 /nai3 参数\n"
                f"style={params['style']} size={params['size']}\n"
                + (f"notes: {notes}\n" if notes else "")
            )

        async for r in self._run_generate(
            event,
            params,
            command="nai3",
            raw_input=raw,
            header=header,
            show_tag_after=True,
            compact_start_sent=compact,
        ):
            yield r

    # ---------------- helpers ----------------

    def _parse_nai3_llm_output(self, text: str) -> dict[str, Any]:
        """解析 nai3 输出：优先 JSON；否则把整段双块英文当 tag。"""
        try:
            data = extract_json_object(text)
            tag = str(data.get("tag") or "").strip()
            if tag:
                return data
        except LlmError:
            pass

        # 纯文本双段：tag 行 + 空行 + caption
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json|text)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        if not cleaned:
            raise LlmError("LLM 返回为空")
        return {
            "tag": cleaned,
            "style": None,
            "size": None,
            "steps": None,
            "scale": None,
            "cfg": None,
            "sampler": None,
            "negative": None,
            "notes": "非 JSON，已整段作为 tag",
        }

    @staticmethod
    def _infer_size_from_tag(tag: str) -> str | None:
        low = (tag or "").lower()
        if any(k in low for k in ("horizontal landscape", "landscape image", "wide frame")):
            return "横图"
        if any(k in low for k in ("vertical portrait", "portrait image", "portrait orientation")):
            return "竖图"
        if "square image" in low or "square orientation" in low:
            return "方图"
        return None

    def _params_from_llm_json(self, data: dict[str, Any], *, fallback_tag: str) -> dict[str, Any]:
        style_id = data.get("style")
        if (
            style_id
            and str(style_id).strip().lower() != "default"
            and resolve_style_id(self.style_pack, str(style_id)) is None
        ):
            logger.warning("[NaiPlugin] LLM 返回未知 style，已禁用画风注入: %s", style_id)
            data["style"] = "none"
            note = str(data.get("notes") or "").strip()
            data["notes"] = (
                f"{note}；LLM 返回未知画风，未附加预设"
                if note
                else "LLM 返回未知画风，未附加预设"
            )
        base = self._default_gen_base()
        tag = str(data.get("tag") or fallback_tag).strip() or fallback_tag

        overrides: dict[str, Any] = {
            "steps": self._as_int(data.get("steps")),
            "scale": self._as_float(data.get("scale")),
            "cfg": self._as_float(data.get("cfg")),
            "sampler": data.get("sampler"),
            "negative": data.get("negative"),
        }
        params = merge_gen_params(base, overrides)
        params = self._apply_style(params, data.get("style"))
        params = self._apply_size(params, data.get("size"))
        params["sampler"] = self._sanitize_sampler(params.get("sampler"), base["sampler"])
        # clamp
        params["steps"] = max(1, min(28, int(params["steps"])))
        params["scale"] = float(params["scale"])
        params["cfg"] = max(0.0, min(1.0, float(params["cfg"])))
        params["tag"] = tag
        return params

    @staticmethod
    def _as_int(v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(v: Any) -> float | None:
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    async def _handle_balance(self, event: AstrMessageEvent):
        try:
            data = await self.client.get_balance()
        except Nai2ApiError as e:
            yield event.plain_result(f"查询余额失败: {e}")
            return
        except Exception as e:
            yield event.plain_result(f"查询余额失败: {e}")
            return

        balance = data.get("balance", data.get("points", 0))
        try:
            balance_int = int(float(balance))
        except (TypeError, ValueError):
            balance_int = 0
        enabled = data.get("enabled", True)
        note = data.get("note") or data.get("remark") or ""
        lines = [
            f"剩余点数: {balance_int}",
            f"账号状态: {'正常' if enabled else '已禁用'}",
            f"约可生成: 普通 {balance_int} 张 / 2K {balance_int // 15} 张 / 4K {balance_int // 25} 张",
        ]
        if note:
            lines.append(f"备注: {note}")
        yield event.plain_result("\n".join(lines))

    async def _run_generate(
        self,
        event: AstrMessageEvent,
        params: dict[str, Any],
        *,
        command: str,
        raw_input: str,
        header: str | None = None,
        show_tag_after: bool = False,
        compact_start_sent: bool = False,
    ):
        compact = self._is_compact_mode()
        if header and not compact:
            yield event.plain_result(header)

        if not str(_cfg_get(self.config, "api_key", "")).strip() and not self.client.token:
            yield event.plain_result("未配置 API Key，请在插件配置页填写 Nai2API 密钥（STA1N-...）")
            return

        if compact and not compact_start_sent:
            yield event.plain_result(self._compact_start_message(command))
        elif not compact and bool(_cfg_get(self.config, "show_progress", True)):
            yield event.plain_result(
                f"⏳ 正在生成（{params.get('style')} / {params.get('size')}）…"
            )

        start = time.time()
        try:
            job = await self._generate_job(params)
        except Nai2ApiError as e:
            yield event.plain_result(f"生图失败: {e}")
            return
        except Exception as e:
            logger.exception("[NaiPlugin] generate error")
            yield event.plain_result(f"生图失败: {e}")
            return

        elapsed = time.time() - start
        image_url = job.get("imageUrl") or ""
        if not image_url:
            yield event.plain_result("生图完成但未获得图片 URL")
            return

        yield event.image_result(image_url)

        if compact:
            if bool(_cfg_get(self.config, "compact_send_details", True)):
                details = self._format_generation_details(
                    command, raw_input, params, elapsed
                )
                yield self._compact_details_result(event, details)
            return

        info_bits = [
            f"style={params.get('style')}",
            f"size={params.get('size')}",
            f"{elapsed:.0f}s",
        ]
        footer = "✅ " + " · ".join(info_bits)
        if show_tag_after and bool(_cfg_get(self.config, "nai3_show_prompt", True)):
            tag = params.get("tag") or ""
            # Anima 双段提示词可能很长，展示首段 tag 行 + 总长度
            first_line = tag.splitlines()[0] if tag else ""
            preview = first_line[:180] + ("…" if len(first_line) > 180 else "")
            footer += f"\ntag: {preview}\n(全文 {len(tag)} 字)"
        yield event.plain_result(footer)
