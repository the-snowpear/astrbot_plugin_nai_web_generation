"""Regression tests for prompt and style-prefix isolation."""

from __future__ import annotations

import json
import sys
import types
import unittest
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REGISTERED_LLM_TOOLS = {}


def _install_aiohttp_stub() -> None:
    try:
        import aiohttp  # noqa: F401
    except ModuleNotFoundError:
        aiohttp = types.ModuleType("aiohttp")
        aiohttp.ClientSession = object
        aiohttp.ClientTimeout = object
        aiohttp.TCPConnector = object
        aiohttp.ClientError = Exception
        sys.modules["aiohttp"] = aiohttp


def _install_astrbot_stub() -> None:
    if "astrbot.api" in sys.modules:
        return

    logger = types.SimpleNamespace(
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        exception=lambda *args, **kwargs: None,
    )
    api = types.ModuleType("astrbot.api")
    api.logger = logger
    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    def _llm_tool(name=None, **kwargs):
        def decorator(func):
            REGISTERED_LLM_TOOLS[name or func.__name__] = func
            return func

        return decorator

    event.filter = types.SimpleNamespace(
        command=lambda _name: lambda func: func,
        llm_tool=_llm_tool,
    )
    star = types.ModuleType("astrbot.api.star")

    class Star:
        def __init__(self, context):
            self.context = context

    star.Context = object
    star.Star = Star
    sys.modules["astrbot"] = types.ModuleType("astrbot")
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event
    sys.modules["astrbot.api.star"] = star


_install_aiohttp_stub()
_install_astrbot_stub()

try:
    from llm_helper import LlmHelper  # noqa: E402
    from main import GreedyStr, Main, _cmd_args  # noqa: E402
    from nai_client import Nai2ApiError  # noqa: E402
    from styles import get_artist  # noqa: E402
except ImportError:
    from astrbot_plugin_nai.llm_helper import LlmHelper  # noqa: E402
    from astrbot_plugin_nai.main import GreedyStr, Main, _cmd_args  # noqa: E402
    from astrbot_plugin_nai.nai_client import Nai2ApiError  # noqa: E402
    from astrbot_plugin_nai.styles import get_artist  # noqa: E402


class StyleIsolationTests(unittest.TestCase):
    def test_missing_or_unknown_style_has_no_artist_prefix(self) -> None:
        self.assertEqual(get_artist("doc712", None), ("none", ""))
        self.assertEqual(get_artist("doc712", "not-a-style"), ("none", ""))
        self.assertEqual(get_artist("doc712", "none"), ("none", ""))
        self.assertEqual(get_artist("doc712", "off"), ("none", ""))

    def test_explicit_valid_style_keeps_its_prefix(self) -> None:
        style, artist = get_artist("doc712", "fresh")
        self.assertEqual(style, "fresh")
        self.assertIn("artist:dishwasher1910", artist)

    def test_configured_default_style_applies_when_style_is_omitted(self) -> None:
        plugin = Main.__new__(Main)
        plugin.config = {"style_pack": "doc712", "default_style": "galgame"}
        base = plugin._default_gen_base()
        self.assertEqual(base["style"], "galgame")
        self.assertIn("artist:ningen_mame", base["artist"])
        self.assertEqual(plugin._apply_style(base, None)["style"], "galgame")
        self.assertEqual(plugin._apply_style(base, "fresh")["style"], "fresh")
        self.assertEqual(plugin._apply_style(base, "none")["artist"], "")

    def test_unknown_llm_style_disables_the_artist_prefix(self) -> None:
        plugin = Main.__new__(Main)
        plugin.config = {"style_pack": "doc712", "default_style": "galgame"}
        params = plugin._params_from_llm_json(
            {"tag": "forest cabin", "style": "not-a-style"}, fallback_tag="forest cabin"
        )
        self.assertEqual(params["style"], "none")
        self.assertEqual(params["artist"], "")


class CommandArgumentTests(unittest.TestCase):
    def test_command_signature_uses_the_real_greedystr_type(self) -> None:
        annotation = inspect.signature(Main.cmd_nai).parameters["args"].annotation
        self.assertIs(annotation, GreedyStr)

    def test_full_raw_message_wins_over_a_truncated_greedy_argument(self) -> None:
        event = types.SimpleNamespace(
            message_str="/nai anime  cinematic illustration,   wide panoramic classroom"
        )
        self.assertEqual(
            _cmd_args(event, "anime", "nai"),
            "anime  cinematic illustration,   wide panoramic classroom",
        )

    def test_get_message_str_preserves_internal_whitespace_over_a_truncated_attribute(self) -> None:
        class Event:
            message_str = "/nai anime"

            @staticmethod
            def get_message_str() -> str:
                return "!nai anime\t cinematic illustration,\n  wide panoramic classroom"

        self.assertEqual(
            _cmd_args(Event(), "anime", "nai"),
            "anime\t cinematic illustration,\n  wide panoramic classroom",
        )

    def test_missing_raw_message_falls_back_to_greedy_argument(self) -> None:
        event = types.SimpleNamespace(message_str="")
        self.assertEqual(_cmd_args(event, "anime cinematic illustration", "nai"), "anime cinematic illustration")

    def test_none_default_style_disables_the_artist_prefix(self) -> None:
        plugin = Main.__new__(Main)
        plugin.config = {"style_pack": "doc712", "default_style": "none"}
        base = plugin._default_gen_base()
        self.assertEqual(base["style"], "none")
        self.assertEqual(base["artist"], "")


class Nai3PromptTests(unittest.TestCase):
    def test_no_concrete_character_example_remains(self) -> None:
        prompt_path = ROOT / "prompts" / "nai3_system.txt"
        if not prompt_path.exists():
            prompt_path = ROOT / "astrbot_plugin_nai" / "prompts" / "nai3_system.txt"
        prompt = prompt_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("shoulder-length white hair", prompt)
        self.assertNotIn("countryside wheat field", prompt)
        self.assertNotIn("example tag content", prompt)
        self.assertIn('"tag"', prompt)


class _Provider:
    def __init__(self) -> None:
        self.kwargs = None

    async def text_chat(self, **kwargs):
        self.kwargs = kwargs
        return "ok"


class _Context:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    def get_using_provider(self):
        return self.provider


class ProviderPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_prompt_is_not_duplicated(self) -> None:
        provider = _Provider()
        helper = LlmHelper(context=_Context(provider))
        result = await helper._chat_astrbot(system="SYSTEM_ONLY_ONCE", user="USER_ONLY_ONCE", temperature=0.2)
        self.assertEqual(result, "ok")
        self.assertEqual(provider.kwargs["system_prompt"], "SYSTEM_ONLY_ONCE")
        self.assertEqual(provider.kwargs["prompt"], "USER_ONLY_ONCE")
        self.assertNotIn("SYSTEM_ONLY_ONCE", provider.kwargs["prompt"])


class _ResultEvent:
    def __init__(self, raw: str = "") -> None:
        self.raw = raw

    def get_message_str(self) -> str:
        return self.raw

    def plain_result(self, text: str):
        return ("plain", text)

    def image_result(self, url: str):
        return ("image", url)


class _OneBotGroupEvent(_ResultEvent):
    def __init__(self, raw: str = "") -> None:
        super().__init__(raw)
        self.message_obj = types.SimpleNamespace(
            sender=types.SimpleNamespace(nickname="测试用户")
        )

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_group_id(self) -> str:
        return "123456"

    def get_sender_id(self) -> str:
        return "10001"

    def chain_result(self, chain):
        return ("forward", chain)


class _ImageClient:
    token = "configured-token"

    async def generate(self, **kwargs):
        return {"imageUrl": "https://example.invalid/image.png"}


class _ErrorImageClient(_ImageClient):
    async def generate(self, **kwargs):
        raise Nai2ApiError("upstream unavailable")


class _EmptyImageClient(_ImageClient):
    async def generate(self, **kwargs):
        return {}


class _CaptureImageClient(_ImageClient):
    def __init__(self) -> None:
        self.kwargs = None

    async def generate(self, **kwargs):
        self.kwargs = kwargs
        return await super().generate(**kwargs)


class _SecretErrorImageClient(_ImageClient):
    async def generate(self, **kwargs):
        raise Nai2ApiError("upstream rejected STA1N-do-not-leak")


class _Llm:
    def has_config(self) -> bool:
        return True

    async def chat_json(self, **kwargs):
        return {
            "tag": "nai2 final tag",
            "style": None,
            "size": None,
            "steps": 30,
            "scale": 5.5,
            "cfg": 1,
            "sampler": "k_dpmpp_2m_sde",
            "negative": "nai2 negative",
        }

    async def chat(self, **kwargs):
        return '{"tag":"nai3 final tag","negative":"nai3 negative"}'


class _FailingLlm(_Llm):
    async def chat(self, **kwargs):
        raise RuntimeError("LLM unavailable")


def _plugin_for_messages(*, compact: bool, send_details: bool = True) -> Main:
    plugin = Main.__new__(Main)
    plugin.config = {
        "api_key": "STA1N-config-secret",
        "message_mode": "compact" if compact else "verbose",
        "compact_send_details": send_details,
        "style_pack": "doc712",
        "default_style": "none",
        "default_size": "竖图",
        "model": "nai-diffusion-4-5-full",
        "negative": "default negative",
    }
    plugin.client = _ImageClient()
    plugin.llm = _Llm()
    plugin._nai2_system = ""
    plugin._nai3_system = ""
    plugin._reload_runtime = lambda: None
    return plugin


async def _collect(generator):
    return [item async for item in generator]


class CompactMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_verbose_run_keeps_header_progress_image_and_footer(self) -> None:
        plugin = _plugin_for_messages(compact=False)
        results = await _collect(
            plugin._run_generate(
                _ResultEvent(),
                {"tag": "tag", "artist": "", "size": "竖图", "steps": 28, "scale": 6,
                 "cfg": 0, "sampler": "k_dpmpp_2m_sde", "negative": "negative", "model": "model"},
                command="nai",
                raw_input="tag",
                header="existing header",
            )
        )
        self.assertEqual([kind for kind, _ in results], ["plain", "plain", "image", "plain"])
        self.assertEqual(results[0][1], "existing header")

    async def test_all_commands_are_compact_and_detail_is_optional(self) -> None:
        plugin = _plugin_for_messages(compact=True)
        nai_results = await _collect(
            plugin.cmd_nai(_ResultEvent("/nai direct tag"), "direct tag")
        )
        nai2_results = await _collect(
            plugin.cmd_nai2(_ResultEvent("/nai2 draw a classroom"), "draw a classroom")
        )
        nai3_results = await _collect(
            plugin.cmd_nai3(_ResultEvent("/nai3 rainy street"), "rainy street")
        )
        for results in (nai_results, nai2_results, nai3_results):
            self.assertEqual([kind for kind, _ in results], ["plain", "image", "plain"])

        no_detail_plugin = _plugin_for_messages(compact=True, send_details=False)
        no_detail_results = await _collect(
            no_detail_plugin.cmd_nai(_ResultEvent("/nai direct tag"), "direct tag")
        )
        self.assertEqual([kind for kind, _ in no_detail_results], ["plain", "image"])

    async def test_compact_details_contain_full_safe_parameters(self) -> None:
        plugin = _plugin_for_messages(compact=True)
        long_tag = "tag-" + ("very-long-prompt " * 80)
        params = {
            "tag": long_tag,
            "artist": "artist:example",
            "size": "横图",
            "steps": 35,
            "scale": 6.5,
            "cfg": 2,
            "sampler": "k_dpmpp_2m_sde",
            "negative": "full negative prompt",
            "model": "nai-diffusion-4-5-full",
            "noise_schedule": "karras",
        }
        results = await _collect(
            plugin._run_generate(
                _ResultEvent(), params, command="nai", raw_input="original request"
            )
        )
        details = results[-1][1]
        self.assertIn(long_tag, details)
        self.assertIn("full negative prompt", details)
        self.assertIn("steps=35", details)
        self.assertIn("noise_schedule=karras", details)
        self.assertNotIn("STA1N-config-secret", details)

    async def test_onebot_group_uses_forward_and_other_platforms_fall_back_to_plain(self) -> None:
        components = types.ModuleType("astrbot.api.message_components")

        class Plain:
            def __init__(self, text):
                self.text = text

        class Node:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        components.Plain = Plain
        components.Node = Node
        sys.modules["astrbot.api.message_components"] = components

        plugin = _plugin_for_messages(compact=True)
        details = plugin._format_generation_details("nai", "raw", {}, 1.0)
        self.assertEqual(plugin._compact_details_result(_ResultEvent(), details)[0], "plain")
        self.assertEqual(plugin._compact_details_result(_OneBotGroupEvent(), details)[0], "forward")

    async def test_compact_failures_have_one_start_and_one_error(self) -> None:
        plugin = _plugin_for_messages(compact=True)
        plugin.client = _ErrorImageClient()
        api_results = await _collect(
            plugin.cmd_nai(_ResultEvent("/nai tag"), "tag")
        )
        self.assertEqual([kind for kind, _ in api_results], ["plain", "plain"])
        self.assertIn("生图失败", api_results[-1][1])

        plugin = _plugin_for_messages(compact=True)
        plugin.llm = _FailingLlm()
        llm_results = await _collect(
            plugin.cmd_nai3(_ResultEvent("/nai3 prompt"), "prompt")
        )
        self.assertEqual([kind for kind, _ in llm_results], ["plain", "plain"])
        self.assertIn("LLM 创作失败", llm_results[-1][1])

        plugin = _plugin_for_messages(compact=True)
        plugin.client = _EmptyImageClient()
        empty_results = await _collect(
            plugin.cmd_nai(_ResultEvent("/nai tag"), "tag")
        )
        self.assertEqual([kind for kind, _ in empty_results], ["plain", "plain"])
        self.assertIn("未获得图片 URL", empty_results[-1][1])


class LlmImageToolTests(unittest.IsolatedAsyncioTestCase):
    def test_tool_is_registered_with_complete_docstring_schema(self) -> None:
        self.assertIs(REGISTERED_LLM_TOOLS["nai_generate_image"], Main.nai_generate_image)
        doc = inspect.getdoc(Main.nai_generate_image) or ""
        self.assertIn("Args:", doc)
        for field in ("prompt", "negative_prompt", "style", "size"):
            self.assertIn(f"{field}(string):", doc)

        schema_path = ROOT / "_conf_schema.json"
        if not schema_path.exists():
            schema_path = ROOT / "astrbot_plugin_nai" / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertTrue(schema["enable_llm_tool"]["default"])

    async def test_success_only_yields_image_and_preserves_effective_params(self) -> None:
        plugin = _plugin_for_messages(compact=False)
        plugin.config["default_style"] = "galgame"
        capture = _CaptureImageClient()
        plugin.client = capture
        prompt = "anime  cinematic illustration,   wide panoramic classroom"

        results = await _collect(
            plugin.nai_generate_image(
                _ResultEvent(),
                prompt,
                "",
                "default",
                "横图",
            )
        )

        self.assertEqual(results, [("image", "https://example.invalid/image.png")])
        self.assertEqual(capture.kwargs["tag"], prompt)
        self.assertEqual(capture.kwargs["size"], "横图")
        self.assertEqual(capture.kwargs["negative"], "default negative")
        self.assertIn("artist:ningen_mame", capture.kwargs["artist"])

        capture = _CaptureImageClient()
        plugin.client = capture
        await _collect(
            plugin.nai_generate_image(
                _ResultEvent(),
                "forest cabin",
                "custom negative  prompt",
                "none",
                "方图",
            )
        )
        self.assertEqual(capture.kwargs["artist"], "")
        self.assertEqual(capture.kwargs["negative"], "custom negative  prompt")

        capture = _CaptureImageClient()
        plugin.client = capture
        await _collect(
            plugin.nai_generate_image(
                _ResultEvent(),
                "summer landscape",
                "",
                "fresh",
                "横图",
            )
        )
        self.assertIn("artist:dishwasher1910", capture.kwargs["artist"])

    async def test_omitted_tool_arguments_use_safe_defaults(self) -> None:
        plugin = _plugin_for_messages(compact=False)
        capture = _CaptureImageClient()
        plugin.client = capture

        results = await _collect(
            plugin.nai_generate_image(_ResultEvent(), "simple landscape")
        )
        self.assertEqual(results[0][0], "image")
        self.assertEqual(capture.kwargs["tag"], "simple landscape")
        self.assertEqual(capture.kwargs["size"], "竖图")
        self.assertEqual(capture.kwargs["negative"], "default negative")

        missing_prompt = await _collect(plugin.nai_generate_image(_ResultEvent()))
        self.assertEqual(len(missing_prompt), 1)
        self.assertIsInstance(missing_prompt[0], str)
        self.assertIn("当前人格", missing_prompt[0])

    async def test_failures_return_only_safe_persona_instruction(self) -> None:
        cases = []

        disabled = _plugin_for_messages(compact=False)
        disabled.config["enable_llm_tool"] = False
        cases.append(disabled)

        missing_key = _plugin_for_messages(compact=False)
        missing_key.config["api_key"] = ""
        missing_key.client = types.SimpleNamespace(token="")
        cases.append(missing_key)

        upstream_error = _plugin_for_messages(compact=False)
        upstream_error.client = _SecretErrorImageClient()
        cases.append(upstream_error)

        empty_image = _plugin_for_messages(compact=False)
        empty_image.client = _EmptyImageClient()
        cases.append(empty_image)

        invalid_runtime = _plugin_for_messages(compact=False)
        invalid_runtime._reload_runtime = lambda: (_ for _ in ()).throw(
            ValueError("STA1N-runtime-secret")
        )
        cases.append(invalid_runtime)

        for plugin in cases:
            results = await _collect(
                plugin.nai_generate_image(
                    _ResultEvent(),
                    "1girl, classroom",
                    "",
                    "default",
                    "竖图",
                )
            )
            self.assertEqual(len(results), 1)
            self.assertIsInstance(results[0], str)
            self.assertIn("当前人格", results[0])
            self.assertNotIn("STA1N", results[0])
            self.assertNotIn("Traceback", results[0])


if __name__ == "__main__":
    unittest.main()
