#!/usr/bin/env python3
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from analyze_video_teardown import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    endpoint_variants,
    extract_text,
    get_api_key,
    load_config,
    post_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_PATH = ROOT / "knowledge_base" / "script_generation_prompt.md"
DEFAULT_CONTENT_KNOWLEDGE_PATH = ROOT / "knowledge_base" / "hot_content_knowledge_base.md"
LEGACY_CONTENT_KNOWLEDGE_PATH = ROOT / "knowledge_base" / "video_teardown_knowledge_base.md"
DEFAULT_CONTENT_KNOWLEDGE_CONFIG_PATH = "knowledge_base/hot_content_knowledge_base.md"
LEGACY_CONTENT_KNOWLEDGE_CONFIG_PATH = "knowledge_base/video_teardown_knowledge_base.md"
OUTPUT_ROOT = ROOT / "script_outputs"

PRODUCT_FIELD_LABELS = {
    "market": "市场 / 地区",
    "collection_date": "收集日期",
    "product_name": "产品名",
    "english_name": "英文名",
    "category": "类目",
    "spec": "规格",
    "colors": "色号",
    "action_time": "作用时间",
    "regular_price": "日常价",
    "promo_price": "活动价",
    "top_selling_points": "TOP 3 核心卖点",
    "audience_pain_matrix": "目标人群 x 痛点矩阵",
    "pain_conversion_talk_tracks": "核心痛点与转化话术",
    "tiktok_marketing_angles": "TikTok 营销推广切入点",
    "market_keywords": "市场关键词参考",
    "material_type_suggestions": "适配素材类型建议",
    "notes": "补充备注",
}


def log(message):
    print(message, flush=True)


def resolve_project_path(value, default_path=None):
    raw_value = str(value or "").strip()
    if not raw_value and default_path:
        return default_path.resolve()
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def read_text_file(path):
    return path.read_text(encoding="utf-8").strip()


def normalize_content_knowledge_path(value):
    text = str(value or "").strip()
    if not text or text == LEGACY_CONTENT_KNOWLEDGE_CONFIG_PATH:
        return DEFAULT_CONTENT_KNOWLEDGE_CONFIG_PATH
    return text


def get_prompt_template(config):
    prompt = str(config.get("script_generation_prompt", "") or "").strip()
    if prompt:
        return prompt
    prompt_path = resolve_project_path(config.get("script_generation_prompt_path"), DEFAULT_PROMPT_PATH)
    if not prompt_path.exists():
        raise SystemExit(f"改写提示词文件不存在: {prompt_path}")
    return read_text_file(prompt_path)


def get_content_knowledge_base(config):
    knowledge_text = str(config.get("content_knowledge_base", "") or "").strip()
    if knowledge_text:
        return knowledge_text
    knowledge_path = resolve_project_path(
        normalize_content_knowledge_path(
            config.get("content_knowledge_base_path")
            or config.get("video_teardown_knowledge_base_path")
            or DEFAULT_CONTENT_KNOWLEDGE_CONFIG_PATH
        ),
        DEFAULT_CONTENT_KNOWLEDGE_PATH,
    )
    candidates = [knowledge_path]
    if knowledge_path != DEFAULT_CONTENT_KNOWLEDGE_PATH:
        candidates.append(DEFAULT_CONTENT_KNOWLEDGE_PATH)
    if LEGACY_CONTENT_KNOWLEDGE_PATH not in candidates:
        candidates.append(LEGACY_CONTENT_KNOWLEDGE_PATH)
    for candidate in candidates:
        if candidate.exists():
            return read_text_file(candidate)
    return ""


def product_profile_to_markdown(profile):
    lines = []
    for key, label in PRODUCT_FIELD_LABELS.items():
        value = str((profile or {}).get(key, "") or "").strip()
        if value:
            lines.append(f"## {label}\n{value}")
    return "\n\n".join(lines).strip() or "未填写产品信息。"


def safe_output_name(value):
    text = str(value or "").strip() or "product_script"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text).strip("_") or "product_script"


def build_generation_prompt(config):
    reference_path = resolve_project_path(config.get("script_reference_analysis_path"))
    if not reference_path.exists():
        raise SystemExit(f"请先选择有效的竞品视频拆解结果: {reference_path}")
    if reference_path.suffix.lower() != ".md":
        raise SystemExit(f"竞品视频拆解结果必须是 Markdown 文件: {reference_path.name}")

    prompt_template = get_prompt_template(config)
    content_knowledge = get_content_knowledge_base(config)
    product_manual = product_profile_to_markdown(config.get("product_profile", {}))
    competitor_teardown = read_text_file(reference_path)
    manual_reference_case = str(config.get("script_reference_case", "") or "").strip()

    country = str(config.get("script_country", "") or config.get("country", "") or "").strip()
    target_language = str(config.get("script_target_language", "") or "").strip()
    total_duration = str(config.get("script_total_duration", "") or "40s").strip()
    hook_duration = str(config.get("script_hook_duration", "") or "8s").strip()
    material_framework = str(config.get("script_material_framework", "") or "").strip()
    audio_emotion = str(config.get("script_audio_emotion", "") or "").strip()

    variables = f"""# 自动导入变量

国家/地区：
{country or "待确认"}

产品手册信息：
{product_manual}

爆款内容知识库：
{content_knowledge or "未填写爆款内容知识库。请优先参考竞品视频拆解结果，但后续建议补充素材类型、原生感、转化逻辑等长期知识。"}

素材框架：
{material_framework or "请从竞品视频拆解结果中提取主框架；如果拆解结果沉淀了新素材类型，则优先沿用该新素材类型。"}

参考案例：
{manual_reference_case or "以下竞品视频拆解结果即为本次复刻参考案例，请平移其心理诱因、情绪节奏、转场力度和话术杀伤力。"}

竞品视频拆解结果：
{competitor_teardown}

音频情绪强度：
{audio_emotion or "请参考竞品视频拆解结果中的情绪与语调，保持同等强度。"}

目标语言：
{target_language or "待确认"}

视频总时长/黄金钩子时长：
{total_duration} / {hook_duration}
"""

    return f"""{variables}

---

# 改写提示词

{prompt_template}

---

# 本次额外约束

- 你正在做的是“脚本产出”：把竞品爆款视频的底层逻辑、情绪节奏、转场力度和话术杀伤力，改写成适配我方产品的新带货视频脚本。
- 必须同时参考“改写提示词、竞品视频拆解结果、产品手册信息、爆款内容知识库”四类输入；其中爆款内容知识库负责约束素材框架、原生感、转化逻辑和复刻边界。
- 竞品里的旧产品、旧痛点、旧机制不能照搬；必须映射到“产品手册信息”中的我方产品、人群、痛点、卖点、价格和适配场景。
- 不要输出拆解报告，不要解释你怎么思考，直接输出可拍摄脚本。
- 每个镜头都必须保留完整的画面、动作、光线、音效、音频文案、中文翻译和语速。
"""


def build_payload(prompt, max_output_tokens):
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.65,
            "maxOutputTokens": max_output_tokens,
        },
    }


def generate_script(config, args):
    api_key = get_api_key(config)
    if not api_key:
        raise SystemExit("缺少 API Key：请设置 MODELMESH_API_KEY，或在 app_config.json 写入 modelmesh_api_key")

    prompt = build_generation_prompt(config)
    if args.dry_run:
        log(f"脚本产出完整上下文长度: {len(prompt)} 字符")
        log("dry-run 完成，未调用模型")
        return prompt, {}, "dry-run", "text"

    model = args.model or config.get("script_generation_model") or config.get("video_analysis_model") or DEFAULT_MODEL
    base_url = args.base_url or config.get("modelmesh_base_url") or DEFAULT_BASE_URL
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    log("开始脚本产出请求")
    log(f"模型: {model}")
    log(f"接口: {base_url.rstrip('/')}/v1beta/models/...:generateContent")
    log(f"参考拆解: {Path(config.get('script_reference_analysis_path', '')).name}")

    last_error = None
    for url, endpoint_style in endpoint_variants(base_url, model):
        log(f"尝试接口格式: {endpoint_style}")
        payload = build_payload(prompt, args.max_output_tokens)
        status, response = post_json(url, headers, payload, args.timeout)
        if 200 <= status < 300:
            return extract_text(response), response, endpoint_style, "text"
        last_error = {"status": status, "response": response, "endpoint_style": endpoint_style}
        message = response.get("error") if isinstance(response, dict) else response
        log(f"  未成功，HTTP {status}: {str(message)[:220]}")
        time.sleep(0.5)

    raise RuntimeError(f"所有 Gemini 原生接口尝试均失败: {json.dumps(last_error, ensure_ascii=False)[:1200]}")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a product TikTok script from product info and competitor teardown.")
    parser.add_argument("--model", default="", help=f"模型名，默认复用配置或 {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default="", help=f"中转 API base，默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT), help="脚本产出结果输出目录")
    parser.add_argument("--timeout", type=int, default=240, help="单次请求超时时间，秒")
    parser.add_argument("--max-output-tokens", type=int, default=32768)
    parser.add_argument("--dry-run", action="store_true", help="只组装提示词并检查参数，不调用模型")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()
    text, raw_response, endpoint_style, field_style = generate_script(config, args)

    if args.dry_run:
        return

    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    profile = config.get("product_profile", {}) or {}
    product_name = profile.get("english_name") or profile.get("product_name") or "product_script"
    language = config.get("script_target_language") or "target_language"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{timestamp}_{safe_output_name(product_name)}_{safe_output_name(language)}"
    output_path = output_root / f"{stem}.md"
    raw_path = output_root / f"{stem}.raw.json"
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log(f"脚本产出成功: endpoint={endpoint_style}, field={field_style}")
    log(f"脚本结果: {output_path}")
    log(f"原始响应: {raw_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"脚本产出失败: {exc}")
        sys.exit(1)
