"""双套画风预设与尺寸映射。"""

from __future__ import annotations

from typing import Any

# ---------- 尺寸与点数 ----------

SIZE_COST: dict[str, int] = {
    "竖图": 1,
    "横图": 1,
    "方图": 1,
    "2K竖图": 15,
    "2K横图": 15,
    "2K方图": 15,
    "4K竖图": 25,
    "4K横图": 25,
    "4K方图": 25,
}

VALID_SIZES = set(SIZE_COST.keys())

SIZE_ALIASES: dict[str, str] = {
    "portrait": "竖图",
    "landscape": "横图",
    "square": "方图",
    "vertical": "竖图",
    "horizontal": "横图",
    "2kportrait": "2K竖图",
    "2klandscape": "2K横图",
    "2ksquare": "2K方图",
    "4kportrait": "4K竖图",
    "4klandscape": "4K横图",
    "4ksquare": "4K方图",
}

# ---------- 默认负面词（与 nai.sta1n.cn /api/settings 一致） ----------

DEFAULT_NEGATIVE = (
    "{{{{bad anatomy}}}},{bad feet},bad hands,{{{bad proportions}}},"
    "{blurry},cloned face,cropped,{{{deformed}}},{{{disfigured}}},"
    "error,{{{extra arms}}},{extra digit},{{{extra legs}}},"
    "extra limbs,{{extra limbs}},{fewer digits},{{{fused fingers}}},"
    "gross proportions,jpeg artifacts,{{{{long neck}}}},low quality,"
    "{malformed limbs},{{missing arms}},{missing fingers},"
    "{{missing legs}},mutated hands,{{{mutation}}},normal quality,"
    "poorly drawn face,poorly drawn hands,signature,text,"
    "{{too many fingers}},{{{ugly}}},username,watermark,worst quality"
)

VALID_SAMPLERS = {
    "k_dpmpp_2m_sde",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "k_dpmpp_2s_ancestral",
    "k_euler_ancestral",
    "k_euler",
}

# ``artist`` is a positive prompt prefix in Nai2API, not display metadata.
# Keep the absence of a selected preset explicit so callers never fall back to
# a strong style prompt by accident.
NO_STYLE_ID = "none"

# ---------- 官网当前预设（app.js） ----------

STYLE_PACK_WEBSITE: dict[str, dict[str, str]] = {
    "fresh": {
        "label": "韩漫小清新风",
        "artist": (
            "masterpiece, best quality,[[[artist:dishwasher1910]]], "
            "{{yd_(orange_maru)}}, [artist:ciloranko], [artist:sho_(sho_lwlw)], "
            "[ningen mame], soft lighting,year 2024"
        ),
    },
    "comicDoujin": {
        "label": "漫画同人风",
        "artist": (
            "masterpiece, best quality, very aesthetic, modern Japanese anime, "
            "official anime art, anime key visual, anime screencap, soft cel shading, "
            "soft anime coloring, smooth color transitions, natural skin tones, "
            "restrained color palette, slightly desaturated, muted colors, "
            "soft ambient lighting, gentle contrast, subtle gradients, subtle bloom, "
            "detailed anime background"
        ),
    },
    "2.5d": {
        "label": "2.5D唯美风",
        "artist": (
            "0.9::misaka_12003-gou ::, dino_(dinoartforame), wanke, liduke, year 2025, "
            "realistic, 4k, -2::green ::, textless version, The image is highly intricate "
            "finished drawn. 1.35::A highly finished photo-style artwork that has "
            "lively color, graphic texture, realistic skin surface, and lifelike flesh "
            "with little obliques::. 1.63::photorealistic::, 1.63::photo(medium)::, "
            "\\n20::best quality, absurdres, very aesthetic, detailed, masterpiece::,, "
            "very aesthetic, masterpiece, no text,"
        ),
    },
    "lolita25d": {
        "label": "2.5D唯美风（萝）",
        "artist": (
            "20::best quality, absurdres, very aesthetic, detailed, masterpiece::, "
            "20::highly finished::, 10::ultra detailed::, 5::masterpiece::, 5::best quality::, "
            "2.4::kidmo::, 1.2::omone hokoma agm::, 1.1::dino, wanke, liduke::, "
            "0.8::rurudo, mignon, artist:pottsness, artist:toosaka asagi::, "
            "0.7::misaka_12003-gou::, 0.6::artist:chocoan, artist:ciloranko, artist:rhasta, "
            "artist:sho_sho_lwlw::, dino_(dinoartforame), agoto, akakura, "
            "0.9::rurudo, mignon:: year 2025, textless version, no text, "
            "The image is highly intricate finished drawn. "
            "1.35::A highly finished photo-style artwork that has graphic texture, "
            "realistic skin surface, and lifelike flesh with little obliques::, "
            "smooth line, glossy skin, realistic, 4k, "
            "1.63::photorealistic::, 1.63::photo(medium)::, 3::simple background::, "
            "2::depth of field::, 1.5::vivid color, lively color::, desaturated, muted tones, "
            "cinematic desaturation, pale aesthetic, silver-toned, "
            "-2::green::, -1.5::vibrant, colorful, saturated::"
        ),
    },
    "doujin": {
        "label": "本子里番风",
        "artist": (
            "1.4::asanagi::,{{{{{artist:asanagi}}}}},1.2::xiaoluo_xl::,"
            "1.3::Artist: misaka_12003-gou::,1.2::Artist:shexyo::,0.7::Artist:b.sa_(bbbs)::,"
            "1::Artist:qiandaiyiyu::,1.05::artist:natedecock::,1.05::artist:kunaboto::,"
            "0.75::artist:kandata_nijou::,1.05::artist:zer0.zer0 ::,1.05::artist:jasony::,"
            "0.75::misaka_12003-gou ::, dino_(dinoartforame), wanke, liduke, year 2025, "
            "realistic, 4k, -2::green ::, {textless version, The image is highly intricate "
            "finished drawn,write realistically,true to life}, "
            "1.35::A highly finished photo-style artwork that has lively color, graphic "
            "texture, realistic skin surface, and lifelike flesh with little obliques::, "
            "1.63::photorealistic::,3::age slider::,1.63::photo(medium)::, "
            "2::best quality, absurdres, very aesthetic, detailed, masterpiece::,"
            "-4::Muscle definition, abs::"
        ),
    },
    "galgame": {
        "label": "GalGame风",
        "artist": (
            "artist:ningen_mame,, noyu_(noyu23386566),, toosaka asagi,, location,"
            "\\n20::best quality, absurdres, very aesthetic, detailed, masterpiece::,:,, "
            "very aesthetic, masterpiece, no text,"
        ),
    },
}

# ---------- 文档 7.12 增强预设 ----------

STYLE_PACK_DOC712: dict[str, dict[str, str]] = {
    "2.5d": {
        "label": "2.5D唯美风",
        "artist": (
            "20::best quality, absurdres, very aesthetic, detailed, masterpiece::, "
            "20::highly finished::, 10::ultra detailed::, 5::masterpiece::, 5::best quality::, "
            "2.4::kidmo::, 1.2::omone hokoma agm::, 1.1::dino, wanke, liduke::, "
            "0.8::rurudo, mignon, artist:pottsness, artist:toosaka asagi::, "
            "0.7::misaka_12003-gou::, 0.6::artist:chocoan, artist:ciloranko, artist:rhasta, "
            "artist:sho_sho_lwlw::, dino_(dinoartforame), agoto, akakura, year 2025, "
            "textless version, no text, The image is highly intricate finished drawn. "
            "1.35::A highly finished photo-style artwork that has graphic texture, realistic "
            "skin surface, and lifelike flesh with little obliques::, smooth line, glossy skin, "
            "realistic, 4k, 1.63::photorealistic::, 1.63::photo(medium)::, 3::simple background::, "
            "2::depth of field::, 1.5::vivid color, lively color::, desaturated, muted tones, "
            "cinematic desaturation, pale aesthetic, silver-toned, "
            "-2::green::, -1.5::vibrant, colorful, saturated::"
        ),
    },
    "fresh": {
        "label": "韩漫小清新风",
        "artist": (
            "masterpiece, best quality,[[[artist:dishwasher1910]]], "
            "{{yd_(orange_maru)}}, [artist:ciloranko], [artist:sho_(sho_lwlw)], "
            "[ningen mame], soft lighting,year 2024"
        ),
    },
    "doujin": {
        "label": "本子里番风",
        "artist": STYLE_PACK_WEBSITE["doujin"]["artist"],
    },
    "galgame": {
        "label": "GalGame风",
        "artist": STYLE_PACK_WEBSITE["galgame"]["artist"],
    },
    "comicDoujin": {
        "label": "漫画同人风",
        "artist": (
            "masterpiece,best quality,ultra detailed,by 小田武士,by 内尾和正,by あずーる,"
            "TV anime screencap,clean cel shading,soft lineart,subtle bloom glow"
        ),
    },
    "animeOld": {
        "label": "动漫风（旧）",
        "artist": (
            "artist collaboration, 0.70::artist:neemi ::, 0.80::artist:tan (tangent) ::, "
            "1.38::artist:kanda done ::, 1.22::artist:quasarcake ::, 1.22::artist:atdan ::, "
            "0.94::artist:fuumi (radial engine) ::, 1.70::artist:john kafka ::, "
            "0.60::artist:meisansan ::, 0.98::artist:ogipote ::, 0.44::artist:nixeu ::, "
            "0.74::artist:mignon ::, 0.94::artist:rangu ::, 1.18::artist:hiten (hitenkei) ::, "
            "1.24::artist:freng ::, 0.56::artist:miwabe sakura ::, year 2024, perspective"
        ),
    },
    "realistic_loli": {
        "label": "2.5D唯美风（萝）",
        "artist": (
            "20::best quality, absurdres, very aesthetic, detailed, masterpiece::, "
            "20::highly finished::, 10::ultra detailed::, 5::masterpiece::, 5::best quality::, "
            "2.4::kidmo::, 1.2::omone hokoma agm::, 1.1::dino, wanke, liduke::, "
            "0.8::rurudo, mignon, artist:pottsness, artist:toosaka asagi::, "
            "0.7::misaka_12003-gou::, 0.6::artist:chocoan, artist:ciloranko, artist:rhasta, "
            "artist:sho_sho_lwlw::, dino_(dinoartforame), agoto, akakura, "
            "0.9::rurudo, mignon:: year 2025, textless version, no text, "
            "The image is highly intricate finished drawn. "
            "1.35::A highly finished photo-style artwork that has graphic texture, "
            "realistic skin surface, and lifelike flesh with little obliques::, "
            "smooth line, glossy skin, realistic, 4k, "
            "1.63::photorealistic::, 1.63::photo(medium)::, 3::simple background::, "
            "2::depth of field::, 1.5::vivid color, lively color::, desaturated, muted tones, "
            "cinematic desaturation, pale aesthetic, silver-toned, "
            "-2::green::, -1.5::vibrant, colorful, saturated::"
        ),
    },
}

# 跨 pack 别名：用户写了另一套 ID 时尽量映射
STYLE_ALIASES: dict[str, dict[str, str]] = {
    "doc712": {
        "lolita25d": "realistic_loli",
        "vertical": "fresh",
    },
    "website": {
        "realistic_loli": "lolita25d",
        "animeOld": "comicDoujin",
        "vertical": "fresh",
    },
}

STYLE_PACKS: dict[str, dict[str, dict[str, str]]] = {
    "doc712": STYLE_PACK_DOC712,
    "website": STYLE_PACK_WEBSITE,
}


def get_pack(pack: str) -> dict[str, dict[str, str]]:
    return STYLE_PACKS.get(pack, STYLE_PACK_DOC712)


def list_styles(pack: str) -> list[tuple[str, str]]:
    styles = get_pack(pack)
    return [(sid, meta["label"]) for sid, meta in styles.items()]


def resolve_style_id(pack: str, style_id: str | None) -> str | None:
    styles = get_pack(pack)
    if not style_id:
        return None
    sid = style_id.strip()
    if sid.lower() in (NO_STYLE_ID, "off"):
        return NO_STYLE_ID
    if sid in styles:
        return sid
    alias = STYLE_ALIASES.get(pack, {}).get(sid)
    if alias and alias in styles:
        return alias
    # 大小写不敏感
    lower_map = {k.lower(): k for k in styles}
    if sid.lower() in lower_map:
        return lower_map[sid.lower()]
    return None


def get_artist(pack: str, style_id: str | None) -> tuple[str, str]:
    """返回 (resolved_style_id, artist_string)，未知或未选 style 不注入前缀。"""
    styles = get_pack(pack)
    sid = resolve_style_id(pack, style_id)
    if sid is None or sid not in styles:
        return NO_STYLE_ID, ""
    return sid, styles[sid]["artist"]


def normalize_size(
    size: str | None,
    *,
    default: str = "竖图",
    allow_2k: bool = True,
    allow_4k: bool = True,
) -> str:
    if not size:
        return default if default in VALID_SIZES else "竖图"
    raw = size.strip()
    mapped = SIZE_ALIASES.get(raw.lower(), raw)
    if mapped not in VALID_SIZES:
        return default if default in VALID_SIZES else "竖图"
    if mapped.startswith("4K") and not allow_4k:
        return mapped.replace("4K", "")
    if mapped.startswith("2K") and not allow_2k:
        return mapped.replace("2K", "")
    return mapped


def size_cost(size: str) -> int:
    return SIZE_COST.get(size, 1)


def styles_help_text(pack: str) -> str:
    lines = [
        f"当前画风包: {pack}",
        "可用画风 ID:",
        "  · none  — 不附加画风预设（默认）",
        "  · default  — 使用配置页的默认画风",
    ]
    for sid, label in list_styles(pack):
        lines.append(f"  · {sid}  — {label}")
    if pack == "doc712":
        lines.append("提示: realistic_loli ≈ 官网 lolita25d")
    else:
        lines.append("提示: lolita25d ≈ 文档包 realistic_loli")
    return "\n".join(lines)


def merge_gen_params(
    base: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合并生成参数，overrides 中 None 不覆盖。"""
    out = dict(base)
    if not overrides:
        return out
    for k, v in overrides.items():
        if v is not None and v != "":
            out[k] = v
    return out
