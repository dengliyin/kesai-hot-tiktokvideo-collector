#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "fastmoss_config.json"
OUTPUT_ROOT = ROOT / "analysis"

DEFAULT_MODEL = "google/gemini-3-flash"
DEFAULT_BASE_URL = "https://router.shengsuanyun.com/api"
DEFAULT_PROMPT = """请用中文简要分析这个短视频，确认你能看到视频内容。
输出三部分：
1. 视频里出现了什么画面
2. 是否有人声/字幕/产品展示
3. 适合做爆款拆解的关键信息
"""


def log(message):
    print(message, flush=True)


def load_config():
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_api_key(config):
    return (
        os.environ.get("MODELMESH_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or config.get("modelmesh_api_key")
        or config.get("gemini_api_key")
        or ""
    )


def get_prompt(args, config):
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    if os.environ.get("VIDEO_TEARDOWN_PROMPT"):
        return os.environ["VIDEO_TEARDOWN_PROMPT"]
    if config.get("video_analysis_prompt"):
        return config["video_analysis_prompt"]
    return DEFAULT_PROMPT


def guess_mime_type(video_path):
    mime_type, _ = mimetypes.guess_type(str(video_path))
    return mime_type or "video/mp4"


def extract_text(response):
    texts = []
    for candidate in response.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    if texts:
        return "\n".join(texts)
    if "text" in response:
        return str(response["text"])
    return json.dumps(response, ensure_ascii=False, indent=2)


def post_json(url, headers, payload, timeout):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body}
        return exc.code, parsed


def build_payload(prompt, video_path, field_style, max_output_tokens):
    video_data = base64.b64encode(video_path.read_bytes()).decode("ascii")
    mime_type = guess_mime_type(video_path)
    if field_style == "snake":
        video_part = {"inline_data": {"mime_type": mime_type, "data": video_data}}
    else:
        video_part = {"inlineData": {"mimeType": mime_type, "data": video_data}}

    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    video_part,
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max_output_tokens,
        },
    }


def endpoint_variants(base_url, model):
    base_url = base_url.rstrip("/")
    encoded_model = urllib.parse.quote(model, safe="")
    raw_model = model.strip("/")
    return [
        (f"{base_url}/v1beta/models/{encoded_model}:generateContent", "encoded-model"),
        (f"{base_url}/v1beta/models/{raw_model}:generateContent", "raw-model"),
    ]


def analyze_video(video_path, config, args):
    api_key = get_api_key(config)
    if not api_key:
        raise SystemExit("缺少 API Key：请设置 MODELMESH_API_KEY，或在 fastmoss_config.json 写入 modelmesh_api_key")

    model = args.model or config.get("video_analysis_model") or DEFAULT_MODEL
    base_url = args.base_url or config.get("modelmesh_base_url") or DEFAULT_BASE_URL
    prompt = get_prompt(args, config)
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    log("开始 Gemini 视频拆解请求")
    log(f"视频文件: {video_path.name}")
    log(f"视频大小: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
    log(f"模型: {model}")
    log(f"接口: {base_url.rstrip('/')}/v1beta/models/...:generateContent")

    last_error = None
    for url, endpoint_style in endpoint_variants(base_url, model):
        for field_style in ("snake", "camel"):
            log(f"尝试接口格式: {endpoint_style}, 字段格式: {field_style}")
            payload = build_payload(prompt, video_path, field_style, args.max_output_tokens)
            status, response = post_json(url, headers, payload, args.timeout)
            if 200 <= status < 300:
                return extract_text(response), response, endpoint_style, field_style
            last_error = {"status": status, "response": response, "endpoint_style": endpoint_style, "field_style": field_style}
            message = response.get("error") if isinstance(response, dict) else response
            log(f"  未成功，HTTP {status}: {str(message)[:220]}")
            time.sleep(0.5)

    raise RuntimeError(f"所有 Gemini 原生接口尝试均失败: {json.dumps(last_error, ensure_ascii=False)[:1200]}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run a minimal Gemini video teardown test on one local MP4.")
    parser.add_argument("video", help="本地 MP4 文件路径")
    parser.add_argument("--model", default="", help=f"模型名，默认 {DEFAULT_MODEL}")
    parser.add_argument("--base-url", default="", help=f"中转 API base，默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--prompt", default="", help="直接传入测试提示词")
    parser.add_argument("--prompt-file", default="", help="从本地文件读取提示词")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT), help="分析结果输出目录")
    parser.add_argument("--timeout", type=int, default=180, help="单次请求超时时间，秒")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    return parser.parse_args()


def main():
    args = parse_args()
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        raise SystemExit(f"视频不存在: {video_path}")
    if video_path.suffix.lower() != ".mp4":
        log("提示: 文件不是 .mp4 后缀，将继续按 MIME 自动识别")

    config = load_config()
    text, raw_response, endpoint_style, field_style = analyze_video(video_path, config, args)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}_gemini_teardown_test.md"
    raw_path = output_dir / f"{video_path.stem}_gemini_teardown_test.raw.json"
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log(f"测试成功: endpoint={endpoint_style}, field={field_style}")
    log(f"拆解结果: {output_path}")
    log(f"原始响应: {raw_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"测试失败: {exc}")
        sys.exit(1)
