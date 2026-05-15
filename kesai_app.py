#!/usr/bin/env python3
import json
import html
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "app_config.json"
LEGACY_CONFIG_PATH = ROOT / "fastmoss_config.json"
STORAGE_DIR = ROOT / "storage"
DOWNLOAD_DIR = ROOT / "downloads"
ANALYSIS_DIR = ROOT / "analysis"
SCRIPT_OUTPUT_DIR = ROOT / "script_outputs"
ADAPTED_SCRIPT_DIR = ROOT / "adapted_scripts"
ASSEMBLED_VIDEO_DIR = ROOT / "assembled_videos"
PUBLISH_RECORD_DIR = ROOT / "publish_records"
METRICS_DIR = ROOT / "metrics"
SCRIPT_OPTIMIZATION_DIR = ROOT / "script_optimizations"
KNOWLEDGE_BASE_DIR = ROOT / "knowledge_base"
DEFAULT_TEARDOWN_KNOWLEDGE_BASE_PATH = KNOWLEDGE_BASE_DIR / "hot_content_knowledge_base.md"
LEGACY_TEARDOWN_KNOWLEDGE_BASE_PATH = KNOWLEDGE_BASE_DIR / "video_teardown_knowledge_base.md"
DEFAULT_TEARDOWN_KNOWLEDGE_BASE_CONFIG_PATH = "knowledge_base/hot_content_knowledge_base.md"
LEGACY_TEARDOWN_KNOWLEDGE_BASE_CONFIG_PATH = "knowledge_base/video_teardown_knowledge_base.md"
DEFAULT_SCRIPT_GENERATION_PROMPT_PATH = KNOWLEDGE_BASE_DIR / "script_generation_prompt.md"
HOST = "127.0.0.1"
PORT = int(os.environ.get("KESAI_APP_PORT", "8765"))

PRODUCT_PROFILE_FIELDS = [
    "market",
    "collection_date",
    "product_name",
    "english_name",
    "category",
    "spec",
    "colors",
    "action_time",
    "regular_price",
    "promo_price",
    "top_selling_points",
    "audience_pain_matrix",
    "pain_conversion_talk_tracks",
    "tiktok_marketing_angles",
    "market_keywords",
    "material_type_suggestions",
    "notes",
]
DEFAULT_PRODUCT_PROFILE = {field: "" for field in PRODUCT_PROFILE_FIELDS}
LEGACY_PRODUCT_PROFILE_ALIASES = {
    "product_name": "name",
    "top_selling_points": "selling_points",
    "audience_pain_matrix": "target_audience",
    "pain_conversion_talk_tracks": "pain_points",
    "tiktok_marketing_angles": "usage_scenarios",
    "promo_price": "price_offer",
    "material_type_suggestions": "tone",
}

DEFAULT_CONFIG = {
    "phone": "",
    "password": "",
    "keyword": "",
    "country": "马来西亚",
    "category_path": ["美妆个护", "头部护理与造型", "染发用品"],
    "product_limit": 3,
    "videos_per_product": 20,
    "show_browser": False,
    "modelmesh_api_key": "",
    "modelmesh_base_url": "https://router.shengsuanyun.com/api",
    "video_analysis_model": "google/gemini-3-flash",
    "video_analysis_prompt": "",
    "video_teardown_knowledge_base_path": DEFAULT_TEARDOWN_KNOWLEDGE_BASE_CONFIG_PATH,
    "video_analysis_max_output_tokens": 32768,
    "analysis_input_path": "",
    "script_generation_prompt_path": "knowledge_base/script_generation_prompt.md",
    "script_reference_analysis_path": "",
    "script_country": "",
    "script_material_framework": "",
    "script_reference_case": "",
    "script_audio_emotion": "",
    "script_target_language": "",
    "script_total_duration": "40s",
    "script_hook_duration": "8s",
    "script_adaptation_input_path": "",
    "script_adaptation_target_model": "veo",
    "script_adaptation_segment_seconds": 8,
    "script_adaptation_notes": "",
    "clip_assembly_input_dir": "",
    "clip_assembly_output_name": "",
    "clip_assembly_notes": "",
    "video_publish_input_path": "",
    "video_publish_account": "",
    "video_publish_caption": "",
    "video_publish_tags": "",
    "video_publish_mode": "manual_record",
    "data_recovery_input_path": "",
    "data_recovery_manual_metrics": "",
    "script_optimization_input_path": "",
    "script_optimization_metrics_path": "",
    "script_optimization_notes": "",
    "product_profile": DEFAULT_PRODUCT_PROFILE.copy(),
}


class JobManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.task = None
        self.started_at = None
        self.finished_at = None
        self.exit_code = None
        self.logs = []

    def start(self, task, command):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise RuntimeError(f"已有任务正在运行: {self.task}")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            self.logs = [f"任务启动: {task}"]
            self.task = task
            self.started_at = time.time()
            self.finished_at = None
            self.exit_code = None
            self.process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self):
        process = self.process
        if not process or not process.stdout:
            return
        for line in process.stdout:
            with self.lock:
                self.logs.append(line.rstrip())
                self.logs = self.logs[-1000:]
        exit_code = process.wait()
        with self.lock:
            self.exit_code = exit_code
            self.finished_at = time.time()
            self.logs.append(f"任务结束，退出码: {exit_code}")

    def stop(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.logs.append("已请求停止任务")
                return True
            return False

    def status(self):
        with self.lock:
            running = bool(self.process and self.process.poll() is None)
            return {
                "running": running,
                "task": self.task,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "logs": self.logs[-400:],
            }


JOBS = JobManager()


def load_config():
    config_path = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            config = json.load(f)
        merged = DEFAULT_CONFIG | config
        merged["video_teardown_knowledge_base_path"] = normalize_teardown_knowledge_base_path(
            merged.get("video_teardown_knowledge_base_path")
        )
        merged["product_profile"] = normalize_product_profile(merged.get("product_profile", {}))
        return merged
    return DEFAULT_CONFIG.copy()


def normalize_teardown_knowledge_base_path(value):
    text = str(value or "").strip()
    if not text or text == LEGACY_TEARDOWN_KNOWLEDGE_BASE_CONFIG_PATH:
        return DEFAULT_TEARDOWN_KNOWLEDGE_BASE_CONFIG_PATH
    return text


def normalize_product_profile(profile):
    if not isinstance(profile, dict):
        profile = {}
    normalized = {}
    for field in PRODUCT_PROFILE_FIELDS:
        value = profile.get(field, "")
        if not value and field in LEGACY_PRODUCT_PROFILE_ALIASES:
            value = profile.get(LEGACY_PRODUCT_PROFILE_ALIASES[field], "")
        normalized[field] = str(value or "")
    return normalized


def save_config(config):
    config = load_config() | config
    category_path = config.get("category_path", [])
    if isinstance(category_path, str):
        category_path = [part.strip() for part in category_path.split(">") if part.strip()]
    if len(category_path) < 3:
        raise ValueError("类目路径至少需要三级，例如：美妆个护 > 头部护理与造型 > 染发用品")
    config["category_path"] = category_path
    config["product_limit"] = int(config.get("product_limit", 3))
    config["videos_per_product"] = int(config.get("videos_per_product", 20))
    config["show_browser"] = bool(config.get("show_browser", False))
    config["modelmesh_api_key"] = str(config.get("modelmesh_api_key", ""))
    config["modelmesh_base_url"] = str(config.get("modelmesh_base_url", DEFAULT_CONFIG["modelmesh_base_url"])).strip()
    config["video_analysis_model"] = str(config.get("video_analysis_model", DEFAULT_CONFIG["video_analysis_model"])).strip()
    config["video_analysis_prompt"] = str(config.get("video_analysis_prompt", ""))
    config["video_teardown_knowledge_base_path"] = normalize_teardown_knowledge_base_path(
        config.get("video_teardown_knowledge_base_path", DEFAULT_CONFIG["video_teardown_knowledge_base_path"])
    )
    config["video_analysis_max_output_tokens"] = int(config.get("video_analysis_max_output_tokens", 32768))
    config["analysis_input_path"] = str(config.get("analysis_input_path", "")).strip()
    config["product_profile"] = normalize_product_profile(config.get("product_profile", {}))
    config.pop("analysis_video_limit", None)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config


def resolve_project_path(raw_path, default_path=None):
    raw_path = str(raw_path or "").strip()
    if not raw_path and default_path:
        return default_path.resolve()
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def resolve_teardown_knowledge_base_path(config):
    return resolve_project_path(
        normalize_teardown_knowledge_base_path(
            config.get("video_teardown_knowledge_base_path", DEFAULT_CONFIG["video_teardown_knowledge_base_path"])
        ),
        DEFAULT_TEARDOWN_KNOWLEDGE_BASE_PATH,
    )


def resolve_script_generation_prompt_path(config):
    return resolve_project_path(
        config.get("script_generation_prompt_path", DEFAULT_CONFIG["script_generation_prompt_path"]),
        DEFAULT_SCRIPT_GENERATION_PROMPT_PATH,
    )


def read_teardown_knowledge_base(config):
    path = resolve_teardown_knowledge_base_path(config)
    candidates = [path]
    if path != DEFAULT_TEARDOWN_KNOWLEDGE_BASE_PATH:
        candidates.append(DEFAULT_TEARDOWN_KNOWLEDGE_BASE_PATH)
    if LEGACY_TEARDOWN_KNOWLEDGE_BASE_PATH not in candidates:
        candidates.append(LEGACY_TEARDOWN_KNOWLEDGE_BASE_PATH)
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return ""


def read_script_generation_prompt(config):
    path = resolve_script_generation_prompt_path(config)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_teardown_knowledge_base(config, text):
    path = resolve_teardown_knowledge_base_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or "").rstrip() + "\n", encoding="utf-8")
    return path


def write_script_generation_prompt(config, text):
    path = resolve_script_generation_prompt_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or "").rstrip() + "\n", encoding="utf-8")
    return path


def config_payload():
    config = load_config()
    config["script_generation_prompt"] = read_script_generation_prompt(config)
    return config


def save_teardown_defaults(payload):
    config = load_config()
    config["modelmesh_api_key"] = str(payload.get("modelmesh_api_key", config.get("modelmesh_api_key", ""))).strip()
    config["modelmesh_base_url"] = str(
        payload.get("modelmesh_base_url", config.get("modelmesh_base_url", DEFAULT_CONFIG["modelmesh_base_url"]))
    ).strip()
    config["video_analysis_model"] = str(
        payload.get("video_analysis_model", config.get("video_analysis_model", DEFAULT_CONFIG["video_analysis_model"]))
    ).strip()
    config["video_analysis_prompt"] = str(payload.get("video_analysis_prompt", config.get("video_analysis_prompt", "")))
    config["video_teardown_knowledge_base_path"] = normalize_teardown_knowledge_base_path(
        payload.get(
            "video_teardown_knowledge_base_path",
            config.get("video_teardown_knowledge_base_path", DEFAULT_CONFIG["video_teardown_knowledge_base_path"]),
        )
    )
    if "analysis_input_path" in payload:
        config["analysis_input_path"] = str(payload.get("analysis_input_path", config.get("analysis_input_path", ""))).strip()
    config["video_analysis_max_output_tokens"] = int(config.get("video_analysis_max_output_tokens", 32768))
    config.pop("analysis_video_limit", None)
    return save_config(config)


def save_script_defaults(payload):
    config = load_config()
    if "video_teardown_knowledge_base_path" in payload:
        config["video_teardown_knowledge_base_path"] = normalize_teardown_knowledge_base_path(
            payload.get("video_teardown_knowledge_base_path", config.get("video_teardown_knowledge_base_path", ""))
        )
    config["script_generation_prompt_path"] = str(
        payload.get(
            "script_generation_prompt_path",
            config.get("script_generation_prompt_path", DEFAULT_CONFIG["script_generation_prompt_path"]),
        )
    ).strip()
    config["script_reference_analysis_path"] = str(
        payload.get("script_reference_analysis_path", config.get("script_reference_analysis_path", ""))
    ).strip()
    config["script_country"] = str(payload.get("script_country", config.get("script_country", ""))).strip()
    config["script_material_framework"] = str(
        payload.get("script_material_framework", config.get("script_material_framework", ""))
    )
    config["script_reference_case"] = str(payload.get("script_reference_case", config.get("script_reference_case", "")))
    config["script_audio_emotion"] = str(payload.get("script_audio_emotion", config.get("script_audio_emotion", ""))).strip()
    config["script_target_language"] = str(
        payload.get("script_target_language", config.get("script_target_language", ""))
    ).strip()
    config["script_total_duration"] = str(payload.get("script_total_duration", config.get("script_total_duration", "40s"))).strip()
    config["script_hook_duration"] = str(payload.get("script_hook_duration", config.get("script_hook_duration", "8s"))).strip()
    if "script_generation_prompt" in payload:
        write_script_generation_prompt(config, payload.get("script_generation_prompt", ""))
    return save_config(config)


CONTENT_WORKFLOW_FIELDS = [
    "script_adaptation_input_path",
    "script_adaptation_target_model",
    "script_adaptation_segment_seconds",
    "script_adaptation_notes",
    "clip_assembly_input_dir",
    "clip_assembly_output_name",
    "clip_assembly_notes",
    "video_publish_input_path",
    "video_publish_account",
    "video_publish_caption",
    "video_publish_tags",
    "video_publish_mode",
    "data_recovery_input_path",
    "data_recovery_manual_metrics",
    "script_optimization_input_path",
    "script_optimization_metrics_path",
    "script_optimization_notes",
]


def save_content_workflow_defaults(payload):
    config = load_config()
    for field in CONTENT_WORKFLOW_FIELDS:
        if field in payload:
            config[field] = payload.get(field, DEFAULT_CONFIG.get(field, ""))
    config["script_adaptation_segment_seconds"] = int(config.get("script_adaptation_segment_seconds") or 8)
    return save_config(config)


def save_product_profile(payload):
    config = load_config()
    profile = payload.get("product_profile", payload)
    config["product_profile"] = normalize_product_profile(profile)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return config["product_profile"]


def file_listing():
    STORAGE_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    ANALYSIS_DIR.mkdir(exist_ok=True)
    SCRIPT_OUTPUT_DIR.mkdir(exist_ok=True)
    ADAPTED_SCRIPT_DIR.mkdir(exist_ok=True)
    ASSEMBLED_VIDEO_DIR.mkdir(exist_ok=True)
    PUBLISH_RECORD_DIR.mkdir(exist_ok=True)
    METRICS_DIR.mkdir(exist_ok=True)
    SCRIPT_OPTIMIZATION_DIR.mkdir(exist_ok=True)
    csv_files = [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        }
        for path in sorted(STORAGE_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    download_dirs = []
    for path in sorted(DOWNLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_dir():
            count = len(list(path.glob("*.mp4")))
            download_dirs.append({"name": path.name, "path": str(path), "count": count, "mtime": path.stat().st_mtime})
    analysis_files = [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        }
        for path in sorted(ANALYSIS_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    script_files = [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "mtime": path.stat().st_mtime,
        }
        for path in sorted(SCRIPT_OUTPUT_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    adapted_script_files = [
        {"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(ADAPTED_SCRIPT_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    assembled_video_files = [
        {"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(ASSEMBLED_VIDEO_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".md", ".json"}
    ]
    publish_record_files = [
        {"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(PUBLISH_RECORD_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    metrics_files = [
        {"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(METRICS_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    optimization_files = [
        {"name": path.name, "path": str(path), "size": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(SCRIPT_OPTIMIZATION_DIR.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    ]
    return {
        "csv_files": csv_files,
        "download_dirs": download_dirs,
        "analysis_files": analysis_files,
        "script_files": script_files,
        "adapted_script_files": adapted_script_files,
        "assembled_video_files": assembled_video_files,
        "publish_record_files": publish_record_files,
        "metrics_files": metrics_files,
        "optimization_files": optimization_files,
    }


def choose_analysis_path(kind="folder"):
    if kind == "file":
        script = 'POSIX path of (choose file with prompt "选择要拆解的 MP4 视频")'
    else:
        script = 'POSIX path of (choose folder with prompt "选择要拆解的视频目录")'
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def choose_script_reference_path():
    script = 'POSIX path of (choose file with prompt "选择竞品视频拆解结果 Markdown")'
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def choose_local_path(kind="file", prompt="选择文件"):
    safe_prompt = str(prompt or "选择文件").replace('"', '\\"')
    if kind == "folder":
        script = f'POSIX path of (choose folder with prompt "{safe_prompt}")'
    else:
        script = f'POSIX path of (choose file with prompt "{safe_prompt}")'
    result = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def validate_analysis_input_path(config):
    raw_path = str(config.get("analysis_input_path", "") or "").strip()
    if not raw_path:
        raise ValueError("请先选择要拆解的 MP4 视频或包含 MP4 的目录")

    target = Path(raw_path).expanduser()
    if not target.exists():
        raise ValueError(f"拆解视频路径不存在: {target}")
    if target.is_file() and target.suffix.lower() != ".mp4":
        raise ValueError(f"选择的文件不是 MP4: {target.name}")
    if target.is_dir() and not any(target.glob("*.mp4")):
        raise ValueError(f"选择的目录里没有 MP4: {target}")


def validate_script_generation_input(config):
    raw_path = str(config.get("script_reference_analysis_path", "") or "").strip()
    if not raw_path:
        raise ValueError("请先选择一个竞品视频拆解结果 Markdown")

    target = Path(raw_path).expanduser()
    if not target.exists():
        raise ValueError(f"竞品视频拆解结果不存在: {target}")
    if target.suffix.lower() != ".md":
        raise ValueError(f"竞品视频拆解结果必须是 Markdown 文件: {target.name}")

    prompt_path = resolve_script_generation_prompt_path(config)
    if not prompt_path.exists():
        raise ValueError(f"改写提示词文件不存在: {prompt_path}")


def open_local_path(raw_path):
    target = Path(unquote(raw_path)).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {target}")
    subprocess.Popen(["open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_html(handler, status, body):
    payload = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>科赛力量爆款收集专家</title>
  <style>
    :root {
      color-scheme: light;
      --accent:#0071e3;
      --accent-hover:#0077ed;
      --danger:#d70015;
      --danger-bg:#fff1f2;
      --line:#d8dce3;
      --soft-line:#edf0f5;
      --text:#1d1d1f;
      --muted:#6e6e73;
      --bg:#f5f5f7;
      --panel:#ffffff;
      --field:#fbfbfd;
      --shadow:0 12px 34px rgba(0,0,0,.06);
    }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; color:var(--text); background:var(--bg); letter-spacing:0; }
    .page { display:none; }
    body[data-page="product"] #productPage,
    body[data-page="collect"] #collectPage,
    body[data-page="analyze"] #analyzePage,
    body[data-page="script"] #scriptPage,
    body[data-page="adapt"] #adaptPage,
    body[data-page="assemble"] #assemblePage,
    body[data-page="publish"] #publishPage,
    body[data-page="metrics"] #metricsPage,
    body[data-page="optimize"] #optimizePage { display:block; }
    header { position:sticky; top:0; z-index:2; min-height:62px; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 28px; background:rgba(255,255,255,.78); border-bottom:1px solid rgba(0,0,0,.08); backdrop-filter:saturate(180%) blur(18px); }
    .headleft { display:flex; align-items:center; gap:22px; min-width:0; }
    h1 { margin:0; font-size:18px; font-weight:700; letter-spacing:0; }
    .nav { display:flex; gap:6px; max-width:74vw; padding:4px; border-radius:999px; background:#eef0f4; overflow-x:auto; scrollbar-width:none; }
    .nav::-webkit-scrollbar { display:none; }
    .nav a { display:inline-flex; align-items:center; min-height:32px; padding:0 13px; border-radius:999px; color:#424245; font-weight:700; text-decoration:none; white-space:nowrap; }
    .nav a.active { background:#fff; color:var(--text); box-shadow:0 1px 3px rgba(0,0,0,.08); }
    .page { max-width:1360px; margin:24px auto 40px; padding:0 22px; }
    .pageintro { display:flex; align-items:flex-end; justify-content:space-between; gap:18px; margin:0 0 16px; }
    .pageintro h2 { margin:0 0 4px; font-size:22px; }
    .workspace { display:grid; grid-template-columns:440px minmax(0,1fr); gap:20px; align-items:start; }
    .workspace.product { grid-template-columns:minmax(0, 1fr) 360px; }
    section { background:var(--panel); border:1px solid rgba(0,0,0,.08); border-radius:8px; padding:20px; box-shadow:var(--shadow); }
    h2 { font-size:16px; line-height:1.25; margin:0 0 16px; font-weight:700; }
    label { display:block; margin:13px 0 6px; color:#424245; font-size:12px; font-weight:700; }
    input, select, textarea { width:100%; border:1px solid #d2d2d7; border-radius:8px; padding:10px 12px; font:inherit; outline:none; background:var(--field); color:var(--text); transition:border-color .16s ease, box-shadow .16s ease, background .16s ease; }
    input, select { min-height:42px; }
    input:focus, select:focus, textarea:focus { border-color:var(--accent); background:#fff; box-shadow:0 0 0 4px rgba(0,113,227,.12); }
    textarea { min-height:78px; resize:vertical; }
    textarea.prompt { min-height:260px; font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; }
    textarea.knowledge { min-height:220px; font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; }
    textarea.scriptprompt { min-height:300px; font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; }
    textarea.tall { min-height:120px; }
    .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .buttons { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
    .sectionhead { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
    .sectionhead h2 { margin:0; }
    .divider { height:1px; background:var(--soft-line); margin:22px 0; }
    .checkline { display:flex; align-items:center; gap:8px; margin-top:14px; font-weight:600; color:#424245; }
    .checkline input { width:auto; min-height:auto; accent-color:var(--accent); }
    button { min-height:38px; border:1px solid rgba(0,0,0,.08); border-radius:8px; padding:9px 14px; font-weight:700; cursor:pointer; background:#f2f2f7; color:var(--accent); box-shadow:0 1px 1px rgba(0,0,0,.04); transition:background .16s ease, transform .16s ease, box-shadow .16s ease; }
    button:hover { background:#e8f2ff; }
    button:active { transform:translateY(1px); box-shadow:none; }
    button.primary, button.blue { background:var(--accent); color:#fff; border-color:var(--accent); }
    button.primary:hover, button.blue:hover { background:var(--accent-hover); }
    button.danger { background:var(--danger-bg); color:var(--danger); border-color:#ffd6dc; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .status { display:flex; gap:8px; align-items:center; color:var(--muted); font-size:13px; }
    .dot { width:10px; height:10px; border-radius:50%; background:#94a3b8; }
    .dot.running { background:#22c55e; box-shadow:0 0 0 5px rgba(34,197,94,.12); }
    pre { height:430px; overflow:auto; margin:0; padding:16px; border-radius:8px; background:#111827; color:#e5e7eb; border:1px solid rgba(255,255,255,.08); white-space:pre-wrap; word-break:break-word; font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; }
    .files { display:grid; grid-template-columns:1fr; gap:12px; margin-top:16px; }
    .filebox { border:1px solid var(--soft-line); border-radius:8px; padding:14px; max-height:260px; overflow:auto; background:#fbfbfd; }
    .filebox h2 { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
    .fileitem { padding:10px 0; border-top:1px solid var(--soft-line); min-width:0; }
    .fileitem:first-child { border-top:0; }
    .filelink { display:block; max-width:100%; color:#1d4f8f; font-weight:700; line-height:1.4; text-decoration:none; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }
    .filelink:hover { color:var(--accent); text-decoration:underline; }
    .filebutton { width:100%; min-height:0; border:0; border-radius:0; padding:0; text-align:left; background:transparent; box-shadow:none; }
    .filebutton:hover { background:transparent; }
    .filebutton:active { transform:none; }
    .filemeta { display:inline-flex; align-items:center; margin-top:5px; padding:2px 7px; border-radius:999px; background:#eef5ff; color:#315f93; font-size:12px; font-weight:600; }
    .empty { padding:14px 0; color:var(--muted); }
    .muted { color:var(--muted); font-size:13px; }
    .infoList { display:grid; gap:12px; margin-top:10px; }
    .infoItem { padding:12px; border:1px solid var(--soft-line); border-radius:8px; background:#fbfbfd; }
    .infoItem strong { display:block; margin-bottom:4px; font-size:13px; }
    .formSection { padding:16px 0; border-top:1px solid var(--soft-line); }
    .formSection:first-of-type { border-top:0; padding-top:0; }
    .formSection h3 { margin:0 0 12px; font-size:15px; line-height:1.3; }
    .pathrow { display:grid; grid-template-columns:1fr 1fr; gap:8px; align-items:center; }
    .pathrow input { grid-column:1 / -1; min-width:0; }
    .pathrow button { width:100%; }
    .toast { position:fixed; top:72px; right:24px; z-index:10; max-width:360px; padding:12px 14px; border-radius:8px; background:rgba(29,29,31,.92); color:#fff; box-shadow:0 14px 36px rgba(0,0,0,.18); opacity:0; pointer-events:none; transform:translateY(-8px); transition:opacity .18s ease, transform .18s ease; }
    .toast.show { opacity:1; transform:translateY(0); }
    .toast.error { background:rgba(215,0,21,.94); }
    @media (max-width:1100px) { .files { grid-template-columns:1fr; } }
    @media (max-width:900px) { header { align-items:flex-start; padding:14px 18px; flex-direction:column; } .workspace, .workspace.product { grid-template-columns:1fr; } .pageintro { align-items:flex-start; flex-direction:column; } .page { padding:0 14px; } }
  </style>
</head>
<body data-page="collect">
  <header>
    <div class="headleft">
      <h1>科赛力量爆款收集专家</h1>
      <nav class="nav" aria-label="功能页面">
        <a id="productNav" href="/product">产品信息</a>
        <a id="collectNav" href="/collect">爆款采集</a>
        <a id="analyzeNav" href="/analyze">视频拆解</a>
        <a id="scriptNav" href="/script">脚本产出</a>
        <a id="adaptNav" href="/adapt">脚本适配</a>
        <a id="assembleNav" href="/assemble">片段组合</a>
        <a id="publishNav" href="/publish">视频发布</a>
        <a id="metricsNav" href="/metrics">数据回收</a>
        <a id="optimizeNav" href="/optimize">脚本优化</a>
      </nav>
    </div>
    <div class="status"><span id="dot" class="dot"></span><span id="statusText">未运行</span></div>
  </header>
  <div id="toast" class="toast"></div>
  <main id="collectPage" class="page">
    <div class="pageintro">
      <div>
        <h2>爆款采集</h2>
        <p class="muted">按关键词、国家和三级类目采集商品关联视频，并自动下载视频素材。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <h2>任务参数</h2>
      <label>手机号</label>
      <input id="phone" autocomplete="off" />
      <label>密码</label>
      <input id="password" type="password" autocomplete="off" />
      <label>关键词</label>
      <input id="keyword" />
      <label>国家/地区</label>
      <input id="country" />
      <label>三级类目路径，用 > 分隔</label>
      <textarea id="category_path"></textarea>
      <div class="grid2">
        <div><label>商品链接数量</label><input id="product_limit" type="number" min="1" /></div>
        <div><label>每商品视频数量</label><input id="videos_per_product" type="number" min="1" /></div>
      </div>
      <label class="checkline"><input id="show_browser" type="checkbox" /> 显示浏览器窗口</label>
      <div class="buttons">
        <button class="primary" onclick="saveConfig()">保存参数</button>
        <button class="blue" onclick="startTask('full')">一键采集</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">默认启动后最小化浏览器窗口，你只看日志。遇到验证码或滑块时，勾选「显示浏览器窗口」后重新运行，手动完成验证即可。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="collectLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>CSV 输出</h2>
          <div id="csvFiles" class="muted">加载中...</div>
        </div>
        <div class="filebox">
          <h2>视频下载目录</h2>
          <div id="downloadDirs" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="productPage" class="page">
    <div class="pageintro">
      <div>
        <h2>产品信息</h2>
        <p class="muted">把你的产品资料沉淀成本地上下文，后面用竞品爆款脚本仿写时直接调用。</p>
      </div>
    </div>
    <div class="workspace product">
      <section>
        <div class="sectionhead">
          <h2>我的产品资料</h2>
          <span class="filemeta">本地保存</span>
        </div>
        <div class="formSection">
          <h3>基础识别</h3>
          <div class="grid2">
            <div>
              <label>市场 / 地区</label>
              <input id="product_market" placeholder="例如：马来西亚 TikTok 市场" />
            </div>
            <div>
              <label>收集日期</label>
              <input id="product_collection_date" placeholder="例如：2026-04-30" />
            </div>
          </div>
          <div class="grid2">
            <div>
              <label>产品名</label>
              <input id="product_product_name" placeholder="例如：泡泡染发洗发水" />
            </div>
            <div>
              <label>英文名</label>
              <input id="product_english_name" placeholder="例如：Bubble Hair Dye Shampoo" />
            </div>
          </div>
          <label>类目</label>
          <input id="product_category" placeholder="例如：美妆个护 > 美发护发 > 染发霜/染发剂" />
          <div class="grid2">
            <div>
              <label>规格</label>
              <input id="product_spec" placeholder="例如：500ml/瓶" />
            </div>
            <div>
              <label>作用时间</label>
              <input id="product_action_time" placeholder="例如：15-25 分钟" />
            </div>
          </div>
          <label>色号</label>
          <textarea id="product_colors" placeholder="例如：自然黑、棕黑色、咖啡色、栗棕色、黑茶色（共5色）"></textarea>
        </div>

        <div class="formSection">
          <h3>定价策略</h3>
          <div class="grid2">
            <div>
              <label>日常价</label>
              <input id="product_regular_price" placeholder="例如：40 马来币" />
            </div>
            <div>
              <label>活动价</label>
              <input id="product_promo_price" placeholder="例如：20.9 马来币" />
            </div>
          </div>
        </div>

        <div class="formSection">
          <h3>TOP 3 核心卖点</h3>
          <textarea id="product_top_selling_points" class="tall" placeholder="按 1/2/3 填写核心卖点，例如：极简操作、天然植物成分、发色自然持久。"></textarea>
        </div>

        <div class="formSection">
          <h3>目标人群 × 痛点矩阵</h3>
          <textarea id="product_audience_pain_matrix" class="tall" placeholder="按人群整理痛点矩阵，例如：白发遮盖族、上班族、年轻爱美人士、居家 DIY 新手。"></textarea>
        </div>

        <div class="formSection">
          <h3>核心痛点与转化话术</h3>
          <textarea id="product_pain_conversion_talk_tracks" class="tall" placeholder="按人群写痛点和话术方向，例如：15分钟泡泡一按一洗、洗澡顺便染发。"></textarea>
        </div>

        <div class="formSection">
          <h3>营销推广切入点（TikTok）</h3>
          <textarea id="product_tiktok_marketing_angles" class="tall" placeholder="填写切入角度、目标人群和关键钩子，例如：15分钟洗掉白发、洗澡顺便染发。"></textarea>
        </div>

        <div class="formSection">
          <h3>西班牙 / 东南亚市场关键词参考</h3>
          <textarea id="product_market_keywords" class="tall" placeholder="例如：bubble hair dye、15 min covering grey、no mess hair dye。"></textarea>
        </div>

        <div class="formSection">
          <h3>适配素材类型建议</h3>
          <textarea id="product_material_type_suggestions" class="tall" placeholder="例如：洗护痛点对比、视觉诊断、15秒快手教程、读心式困惑、暴露缺点。"></textarea>
        </div>

        <div class="formSection">
          <h3>补充备注</h3>
          <textarea id="product_notes" class="tall" placeholder="其他无法归类但生成脚本时必须保留的信息。"></textarea>
        </div>
        <div class="buttons">
          <button class="primary" onclick="saveProductProfile()">保存产品信息</button>
        </div>
        <p class="muted">这些信息只会保存到本地配置文件，后续可以和竞品视频拆解结果一起作为仿写脚本的输入。</p>
      </section>
      <section>
        <h2>后续用途</h2>
        <div class="infoList">
          <div class="infoItem">
            <strong>1. 对齐产品上下文</strong>
            <span class="muted">拆解竞品脚本后，用你的产品卖点替换竞品产品，不会只复刻形式。</span>
          </div>
          <div class="infoItem">
            <strong>2. 控制转化重点</strong>
            <span class="muted">价格、优惠、信任背书和禁用表达会约束脚本生成方向。</span>
          </div>
          <div class="infoItem">
            <strong>3. 支持脚本产出</strong>
            <span class="muted">把「视频拆解结果 + 产品信息」合并，让模型输出你的带货脚本。</span>
          </div>
        </div>
      </section>
    </div>
  </main>
  <main id="analyzePage" class="page">
    <div class="pageintro">
      <div>
        <h2>视频拆解</h2>
        <p class="muted">选择本地 MP4 或包含 MP4 的目录，用保存的模型和提示词拆解爆款视频。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>视频拆解默认设置</h2>
        <span class="filemeta">本地保存</span>
      </div>
      <label>ModelMesh API Key</label>
      <input id="modelmesh_api_key" type="password" autocomplete="off" placeholder="只保存在本地 app_config.json" />
      <label>拆解模型</label>
      <select id="video_analysis_model">
        <option value="google/gemini-3-flash">Gemini 3 Flash Preview</option>
        <option value="google/gemini-3.1-flash-lite-preview">Gemini 3.1 Flash Lite Preview</option>
        <option value="google/gemini-3.1-pro-preview">Gemini 3.1 Pro Preview</option>
        <option value="google/gemini-2.5-flash">Gemini 2.5 Flash</option>
        <option value="google/gemini-2.5-pro">Gemini 2.5 Pro</option>
      </select>
      <label>接口 Base URL</label>
      <input id="modelmesh_base_url" />
      <label>爆款内容知识库文件（拆解 / 改写共用）</label>
      <div class="pathrow">
        <input id="video_teardown_knowledge_base_path" placeholder="knowledge_base/hot_content_knowledge_base.md" />
        <button onclick="openLocalPath(video_teardown_knowledge_base_path.value)">打开文件</button>
      </div>
      <label>拆解视频路径</label>
      <div class="pathrow">
        <input id="analysis_input_path" placeholder="请选择 MP4 视频或包含 MP4 的目录" />
        <button onclick="chooseAnalysisPath('folder')">选择目录</button>
        <button onclick="chooseAnalysisPath('file')">选择视频</button>
      </div>
      <label>爆款视频拆解提示词</label>
      <textarea id="video_analysis_prompt" class="prompt" placeholder="粘贴或修改你的爆款视频拆解提示词；留空时使用最小测试提示词"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveTeardownDefaults()">保存默认设置</button>
        <button class="blue" onclick="startTask('analyze')">拆解视频</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">选择目录时会拆解目录下全部 MP4；选择单个视频时只拆解该视频。爆款内容知识库同时服务于视频拆解和脚本改写。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="analyzeLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>视频拆解结果</h2>
          <div id="analysisFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="scriptPage" class="page">
    <div class="pageintro">
      <div>
        <h2>脚本产出</h2>
        <p class="muted">把竞品视频拆解结果和你的产品信息合并，复刻成适合自家产品的新带货脚本。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>脚本产出参数</h2>
        <span class="filemeta">本地保存</span>
      </div>
      <div class="infoItem">
        <strong>输入结构</strong>
        <span class="muted">脚本产出 = 改写提示词 + 竞品拆解结果 + 产品信息 + 爆款内容知识库。</span>
      </div>
      <label>改写提示词本地文件</label>
      <input id="script_generation_prompt_path" placeholder="knowledge_base/script_generation_prompt.md" />
      <label>竞品视频拆解结果</label>
      <div class="pathrow">
        <input id="script_reference_analysis_path" placeholder="请选择一个视频拆解结果 .md 文件" />
        <button onclick="chooseScriptReferencePath()">选择拆解结果</button>
        <button onclick="openLocalPath(script_reference_analysis_path.value)">打开文件</button>
      </div>
      <div class="grid2">
        <div>
          <label>国家/地区</label>
          <input id="script_country" placeholder="例如：马来西亚" />
        </div>
        <div>
          <label>目标语言</label>
          <input id="script_target_language" placeholder="例如：马来语 / 西班牙语 / 英语" />
        </div>
      </div>
      <div class="grid2">
        <div>
          <label>视频总时长</label>
          <input id="script_total_duration" placeholder="例如：40s" />
        </div>
        <div>
          <label>黄金钩子时长</label>
          <input id="script_hook_duration" placeholder="例如：8s" />
        </div>
      </div>
      <label>音频情绪强度</label>
      <input id="script_audio_emotion" placeholder="例如：毒舌犀利 / 离职博主爆料 / 强度 8" />
      <label>素材框架</label>
      <textarea id="script_material_framework" class="tall" placeholder="可粘贴素材类型序号和框架公式；留空时从竞品拆解结果中自动提取。"></textarea>
      <label>参考案例补充</label>
      <textarea id="script_reference_case" class="tall" placeholder="可粘贴同类型案例全文；留空时直接使用选中的竞品视频拆解结果。"></textarea>
      <label>爆款内容知识库文件（与视频拆解共用）</label>
      <div class="pathrow">
        <input id="script_content_knowledge_base_path" placeholder="knowledge_base/hot_content_knowledge_base.md" />
        <button onclick="openLocalPath(script_content_knowledge_base_path.value)">打开文件</button>
      </div>
      <label>改写提示词内容</label>
      <textarea id="script_generation_prompt" class="scriptprompt" placeholder="这里会读取本地改写提示词；负责规定怎么根据拆解结果和产品信息复刻脚本。"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveScriptDefaults()">保存脚本设置</button>
        <button class="blue" onclick="startTask('script')">生成脚本</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">产品信息来自「产品信息」页；爆款内容知识库和视频拆解共用。生成内容保存在本地，不会提交到 GitHub。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="scriptLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>脚本产出结果</h2>
          <div id="scriptFiles" class="muted">加载中...</div>
        </div>
        <div class="filebox">
          <h2>可选拆解结果</h2>
          <div id="scriptAnalysisFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="adaptPage" class="page">
    <div class="pageintro">
      <div>
        <h2>脚本适配</h2>
        <p class="muted">把成品脚本改写成适合视频生成模型的分段提示词，并同步生成每段首帧图描述。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>适配参数</h2>
        <span class="filemeta">框架版</span>
      </div>
      <label>成品脚本路径</label>
      <div class="pathrow">
        <input id="script_adaptation_input_path" placeholder="选择 script_outputs 中的成品脚本 .md" />
        <button onclick="chooseGenericPath('script_adaptation_input_path','file','选择要适配的成品脚本')">选择脚本</button>
        <button onclick="openLocalPath(script_adaptation_input_path.value)">打开文件</button>
      </div>
      <div class="grid2">
        <div>
          <label>视频生成模型</label>
          <select id="script_adaptation_target_model">
            <option value="veo">Veo</option>
            <option value="kling">可灵</option>
            <option value="runway">Runway</option>
            <option value="pika">Pika</option>
            <option value="custom">自定义</option>
          </select>
        </div>
        <div>
          <label>单片段时长上限（秒）</label>
          <input id="script_adaptation_segment_seconds" type="number" min="1" placeholder="8" />
        </div>
      </div>
      <label>适配备注</label>
      <textarea id="script_adaptation_notes" class="tall" placeholder="例如：每段必须 8 秒内；首帧图要突出 [product]；保持 TikTok 原生感。"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveContentWorkflowDefaults()">保存设置</button>
        <button class="blue" onclick="startTask('adapt')">适配脚本</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">当前先生成片段适配框架；后续可接入模型，把每段自动优化成 Veo/可灵等模型的最终提示词。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="adaptLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>脚本适配结果</h2>
          <div id="adaptedScriptFiles" class="muted">加载中...</div>
        </div>
        <div class="filebox">
          <h2>可选成品脚本</h2>
          <div id="adaptSourceScriptFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="assemblePage" class="page">
    <div class="pageintro">
      <div>
        <h2>片段组合</h2>
        <p class="muted">把生成好的多个视频片段按顺序组合成一条完整视频。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>组合参数</h2>
        <span class="filemeta">框架版</span>
      </div>
      <label>片段目录</label>
      <div class="pathrow">
        <input id="clip_assembly_input_dir" placeholder="选择存放片段 mp4 的文件夹" />
        <button onclick="chooseGenericPath('clip_assembly_input_dir','folder','选择视频片段目录')">选择目录</button>
        <button onclick="openLocalPath(clip_assembly_input_dir.value)">打开目录</button>
      </div>
      <label>输出视频名称</label>
      <input id="clip_assembly_output_name" placeholder="例如：script_v1_test_video" />
      <label>组合备注</label>
      <textarea id="clip_assembly_notes" class="tall" placeholder="例如：按文件名顺序拼接；后续加入片头、字幕、BGM、转场。"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveContentWorkflowDefaults()">保存设置</button>
        <button class="blue" onclick="startTask('assemble')">组合片段</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">如果本机检测到 ffmpeg 且目录内有视频片段，会尝试无转码拼接；否则先生成组合清单和计划。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="assembleLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>组合输出</h2>
          <div id="assembledVideoFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="publishPage" class="page">
    <div class="pageintro">
      <div>
        <h2>视频发布</h2>
        <p class="muted">管理待发布视频、账号、文案和标签；自动发布接口后续按账号授权方式接入。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>发布参数</h2>
        <span class="filemeta">计划/记录</span>
      </div>
      <label>待发布视频</label>
      <div class="pathrow">
        <input id="video_publish_input_path" placeholder="选择组合后的视频 .mp4" />
        <button onclick="chooseGenericPath('video_publish_input_path','file','选择待发布视频')">选择视频</button>
        <button onclick="openLocalPath(video_publish_input_path.value)">打开文件</button>
      </div>
      <div class="grid2">
        <div>
          <label>TikTok 账号</label>
          <input id="video_publish_account" placeholder="账号昵称或内部备注" />
        </div>
        <div>
          <label>发布模式</label>
          <select id="video_publish_mode">
            <option value="manual_record">手动发布记录</option>
            <option value="api_pending">自动发布待接入</option>
          </select>
        </div>
      </div>
      <label>发布文案</label>
      <textarea id="video_publish_caption" class="tall" placeholder="视频 caption / 标题 / 购物车引导。"></textarea>
      <label>标签</label>
      <input id="video_publish_tags" placeholder="#hairdye #beauty #tiktokshop" />
      <div class="buttons">
        <button class="primary" onclick="saveContentWorkflowDefaults()">保存设置</button>
        <button class="blue" onclick="startTask('publish')">生成发布计划</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">当前不会自动登录或发布到 TikTok，只会生成发布计划。等你确认账号管理方式后再接自动发布。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="publishLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>发布记录</h2>
          <div id="publishRecordFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="metricsPage" class="page">
    <div class="pageintro">
      <div>
        <h2>数据回收</h2>
        <p class="muted">把每条发布视频的播放、互动、点击、转化等数据回收成统一记录。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>回收参数</h2>
        <span class="filemeta">框架版</span>
      </div>
      <label>数据文件</label>
      <div class="pathrow">
        <input id="data_recovery_input_path" placeholder="选择平台导出的 CSV，或留空手动填写" />
        <button onclick="chooseGenericPath('data_recovery_input_path','file','选择数据回收 CSV')">选择文件</button>
        <button onclick="openLocalPath(data_recovery_input_path.value)">打开文件</button>
      </div>
      <label>手动数据</label>
      <textarea id="data_recovery_manual_metrics" class="tall" placeholder="例如：视频ID、脚本版本、播放、完播、点赞、评论、点击、成交、GMV。"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveContentWorkflowDefaults()">保存设置</button>
        <button class="blue" onclick="startTask('metrics')">回收数据</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">当前支持先读取 CSV 数值字段并生成汇总；后续可接 TikTok/TikTok Shop/API 或手动导入模板。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="metricsLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>数据回收结果</h2>
          <div id="metricsFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <main id="optimizePage" class="page">
    <div class="pageintro">
      <div>
        <h2>脚本优化</h2>
        <p class="muted">根据同一脚本产出的所有视频数据做加权评估，再反向优化脚本。</p>
      </div>
    </div>
    <div class="workspace">
    <section>
      <div class="sectionhead">
        <h2>优化参数</h2>
        <span class="filemeta">框架版</span>
      </div>
      <label>原脚本路径</label>
      <div class="pathrow">
        <input id="script_optimization_input_path" placeholder="选择要优化的脚本 .md" />
        <button onclick="chooseGenericPath('script_optimization_input_path','file','选择要优化的脚本')">选择脚本</button>
        <button onclick="openLocalPath(script_optimization_input_path.value)">打开文件</button>
      </div>
      <label>数据回收结果</label>
      <div class="pathrow">
        <input id="script_optimization_metrics_path" placeholder="选择 metrics 中的数据回收结果" />
        <button onclick="chooseGenericPath('script_optimization_metrics_path','file','选择数据回收结果')">选择数据</button>
        <button onclick="openLocalPath(script_optimization_metrics_path.value)">打开文件</button>
      </div>
      <label>优化备注</label>
      <textarea id="script_optimization_notes" class="tall" placeholder="例如：更看重成交/GMV；完播低优先重写前3秒；评论低优化争议点。"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveContentWorkflowDefaults()">保存设置</button>
        <button class="blue" onclick="startTask('optimize')">优化脚本</button>
        <button class="danger" onclick="stopTask()">停止任务</button>
      </div>
      <p class="muted">当前先产出加权评估和优化建议框架；后续接入真实发布数据后，再自动生成新脚本版本。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="optimizeLogs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>脚本优化结果</h2>
          <div id="optimizationFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
    </div>
  </main>
  <script>
    const pageMap = {
      '/product': 'product',
      '/collect': 'collect',
      '/analyze': 'analyze',
      '/script': 'script',
      '/adapt': 'adapt',
      '/assemble': 'assemble',
      '/publish': 'publish',
      '/metrics': 'metrics',
      '/optimize': 'optimize'
    };
    const currentPage = pageMap[location.pathname] || 'product';
    document.body.dataset.page = currentPage;
    collectNav.classList.toggle('active', currentPage === 'collect');
    productNav.classList.toggle('active', currentPage === 'product');
    analyzeNav.classList.toggle('active', currentPage === 'analyze');
    scriptNav.classList.toggle('active', currentPage === 'script');
    adaptNav.classList.toggle('active', currentPage === 'adapt');
    assembleNav.classList.toggle('active', currentPage === 'assemble');
    publishNav.classList.toggle('active', currentPage === 'publish');
    metricsNav.classList.toggle('active', currentPage === 'metrics');
    optimizeNav.classList.toggle('active', currentPage === 'optimize');
    const productFields = [
      'market',
      'collection_date',
      'product_name',
      'english_name',
      'category',
      'spec',
      'colors',
      'action_time',
      'regular_price',
      'promo_price',
      'top_selling_points',
      'audience_pain_matrix',
      'pain_conversion_talk_tracks',
      'tiktok_marketing_angles',
      'market_keywords',
      'material_type_suggestions',
      'notes'
    ];

    async function api(path, options={}) {
      const res = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '请求失败');
      return data;
    }
    async function loadConfig() {
      const cfg = await api('/api/config');
      phone.value = cfg.phone || '';
      password.value = cfg.password || '';
      keyword.value = cfg.keyword || '';
      country.value = cfg.country || '';
      category_path.value = (cfg.category_path || []).join(' > ');
      product_limit.value = cfg.product_limit || 3;
      videos_per_product.value = cfg.videos_per_product || 20;
      show_browser.checked = !!cfg.show_browser;
      modelmesh_api_key.value = cfg.modelmesh_api_key || '';
      modelmesh_base_url.value = cfg.modelmesh_base_url || 'https://router.shengsuanyun.com/api';
      video_analysis_model.value = cfg.video_analysis_model || 'google/gemini-3-flash';
      video_teardown_knowledge_base_path.value = cfg.video_teardown_knowledge_base_path || 'knowledge_base/hot_content_knowledge_base.md';
      analysis_input_path.value = cfg.analysis_input_path || '';
      video_analysis_prompt.value = cfg.video_analysis_prompt || '';
      script_generation_prompt_path.value = cfg.script_generation_prompt_path || 'knowledge_base/script_generation_prompt.md';
      script_generation_prompt.value = cfg.script_generation_prompt || '';
      script_content_knowledge_base_path.value = cfg.video_teardown_knowledge_base_path || 'knowledge_base/hot_content_knowledge_base.md';
      script_reference_analysis_path.value = cfg.script_reference_analysis_path || '';
      script_country.value = cfg.script_country || cfg.country || '';
      script_material_framework.value = cfg.script_material_framework || '';
      script_reference_case.value = cfg.script_reference_case || '';
      script_audio_emotion.value = cfg.script_audio_emotion || '';
      script_target_language.value = cfg.script_target_language || '';
      script_total_duration.value = cfg.script_total_duration || '40s';
      script_hook_duration.value = cfg.script_hook_duration || '8s';
      script_adaptation_input_path.value = cfg.script_adaptation_input_path || '';
      script_adaptation_target_model.value = cfg.script_adaptation_target_model || 'veo';
      script_adaptation_segment_seconds.value = cfg.script_adaptation_segment_seconds || 8;
      script_adaptation_notes.value = cfg.script_adaptation_notes || '';
      clip_assembly_input_dir.value = cfg.clip_assembly_input_dir || '';
      clip_assembly_output_name.value = cfg.clip_assembly_output_name || '';
      clip_assembly_notes.value = cfg.clip_assembly_notes || '';
      video_publish_input_path.value = cfg.video_publish_input_path || '';
      video_publish_account.value = cfg.video_publish_account || '';
      video_publish_caption.value = cfg.video_publish_caption || '';
      video_publish_tags.value = cfg.video_publish_tags || '';
      video_publish_mode.value = cfg.video_publish_mode || 'manual_record';
      data_recovery_input_path.value = cfg.data_recovery_input_path || '';
      data_recovery_manual_metrics.value = cfg.data_recovery_manual_metrics || '';
      script_optimization_input_path.value = cfg.script_optimization_input_path || '';
      script_optimization_metrics_path.value = cfg.script_optimization_metrics_path || '';
      script_optimization_notes.value = cfg.script_optimization_notes || '';
      const profile = cfg.product_profile || {};
      productFields.forEach(field => {
        const el = document.getElementById('product_' + field);
        if (el) el.value = profile[field] || '';
      });
    }
    async function saveConfig(silent=false) {
      const payload = {
        phone: phone.value.trim(),
        password: password.value,
        keyword: keyword.value.trim(),
        country: country.value.trim(),
        category_path: category_path.value.split('>').map(x => x.trim()).filter(Boolean),
        product_limit: Number(product_limit.value || 3),
        videos_per_product: Number(videos_per_product.value || 20),
        show_browser: show_browser.checked
      };
      await api('/api/config', {method:'POST', body:JSON.stringify(payload)});
      await refresh();
      if (!silent) alert('参数已保存');
    }
    async function saveTeardownDefaults(silent=false) {
      const payload = {
        modelmesh_api_key: modelmesh_api_key.value.trim(),
        modelmesh_base_url: modelmesh_base_url.value.trim(),
        video_analysis_model: video_analysis_model.value,
        video_teardown_knowledge_base_path: video_teardown_knowledge_base_path.value.trim(),
        analysis_input_path: analysis_input_path.value.trim(),
        video_analysis_prompt: video_analysis_prompt.value
      };
      await api('/api/teardown-defaults', {method:'POST', body:JSON.stringify(payload)});
      await refresh();
      if (!silent) alert('视频拆解默认设置已保存到本地');
    }
    async function saveScriptDefaults(silent=false) {
      const payload = {
        script_generation_prompt_path: script_generation_prompt_path.value.trim(),
        script_generation_prompt: script_generation_prompt.value,
        video_teardown_knowledge_base_path: script_content_knowledge_base_path.value.trim(),
        script_reference_analysis_path: script_reference_analysis_path.value.trim(),
        script_country: script_country.value.trim(),
        script_material_framework: script_material_framework.value,
        script_reference_case: script_reference_case.value,
        script_audio_emotion: script_audio_emotion.value.trim(),
        script_target_language: script_target_language.value.trim(),
        script_total_duration: script_total_duration.value.trim(),
        script_hook_duration: script_hook_duration.value.trim()
      };
      await api('/api/script-defaults', {method:'POST', body:JSON.stringify(payload)});
      await refresh();
      if (!silent) alert('脚本产出设置已保存到本地');
    }
    async function saveContentWorkflowDefaults(silent=false) {
      const payload = {
        script_adaptation_input_path: script_adaptation_input_path.value.trim(),
        script_adaptation_target_model: script_adaptation_target_model.value,
        script_adaptation_segment_seconds: Number(script_adaptation_segment_seconds.value || 8),
        script_adaptation_notes: script_adaptation_notes.value,
        clip_assembly_input_dir: clip_assembly_input_dir.value.trim(),
        clip_assembly_output_name: clip_assembly_output_name.value.trim(),
        clip_assembly_notes: clip_assembly_notes.value,
        video_publish_input_path: video_publish_input_path.value.trim(),
        video_publish_account: video_publish_account.value.trim(),
        video_publish_caption: video_publish_caption.value,
        video_publish_tags: video_publish_tags.value.trim(),
        video_publish_mode: video_publish_mode.value,
        data_recovery_input_path: data_recovery_input_path.value.trim(),
        data_recovery_manual_metrics: data_recovery_manual_metrics.value,
        script_optimization_input_path: script_optimization_input_path.value.trim(),
        script_optimization_metrics_path: script_optimization_metrics_path.value.trim(),
        script_optimization_notes: script_optimization_notes.value
      };
      await api('/api/content-workflow-defaults', {method:'POST', body:JSON.stringify(payload)});
      await refresh();
      if (!silent) alert('内容分发工作流设置已保存到本地');
    }
    async function saveProductProfile(silent=false) {
      try {
        const product_profile = {};
        productFields.forEach(field => {
          const el = document.getElementById('product_' + field);
          product_profile[field] = el ? el.value.trim() : '';
        });
        await api('/api/product-profile', {method:'POST', body:JSON.stringify({product_profile})});
        if (!silent) showToast('产品信息已保存到本地');
      } catch (error) {
        showToast(error.message || '产品信息保存失败', true);
      }
    }
    async function startTask(task) {
      try {
        if (task === 'analyze') {
          if (!analysis_input_path.value.trim()) {
            showToast('请先选择要拆解的 MP4 视频或包含 MP4 的目录', true);
            return;
          }
          await saveTeardownDefaults(true);
        } else if (task === 'script') {
          if (!script_reference_analysis_path.value.trim()) {
            showToast('请先选择竞品视频拆解结果 Markdown', true);
            return;
          }
          await saveScriptDefaults(true);
        } else if (['adapt', 'assemble', 'publish', 'metrics', 'optimize'].includes(task)) {
          await saveContentWorkflowDefaults(true);
        } else {
          await saveConfig(true);
        }
        await api('/api/run/' + task, {method:'POST', body:'{}'});
        await refresh();
      } catch (error) {
        showToast(error.message || '任务启动失败', true);
      }
    }
    async function stopTask() {
      await api('/api/stop', {method:'POST', body:'{}'});
      await refresh();
    }
    async function chooseAnalysisPath(kind) {
      try {
        const res = await api('/api/choose-analysis-path', {method:'POST', body:JSON.stringify({kind})});
        analysis_input_path.value = res.path || '';
        await saveTeardownDefaults(true);
      } catch (error) {
        showToast(error.message || '选择路径失败', true);
      }
    }
    async function chooseScriptReferencePath() {
      try {
        const res = await api('/api/choose-script-reference-path', {method:'POST', body:'{}'});
        script_reference_analysis_path.value = res.path || '';
        await saveScriptDefaults(true);
      } catch (error) {
        showToast(error.message || '选择拆解结果失败', true);
      }
    }
    async function chooseGenericPath(targetId, kind, prompt) {
      try {
        const res = await api('/api/choose-path', {method:'POST', body:JSON.stringify({kind, prompt})});
        const el = document.getElementById(targetId);
        if (el) el.value = res.path || '';
        await saveContentWorkflowDefaults(true);
      } catch (error) {
        showToast(error.message || '选择路径失败', true);
      }
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function showToast(message, isError=false) {
      toast.textContent = message;
      toast.className = 'toast show' + (isError ? ' error' : '');
      clearTimeout(window.toastTimer);
      window.toastTimer = setTimeout(() => { toast.className = 'toast'; }, 2400);
    }
    async function openLocalPath(path) {
      try {
        const result = await api('/api/open-path', {method:'POST', body:JSON.stringify({path})});
        showToast('已打开：' + result.name);
      } catch (error) {
        showToast(error.message || '打开失败', true);
      }
    }
    function openButton(file) {
      const name = escapeHtml(file.name);
      const encodedPath = encodeURIComponent(file.path);
      return `<button class="filelink filebutton" type="button" data-path="${encodedPath}" onclick="openLocalPath(decodeURIComponent(this.dataset.path))" title="${escapeHtml(file.path)}">${name}</button>`;
    }
    function renderFiles(files) {
      if (document.getElementById('csvFiles')) {
        csvFiles.innerHTML = files.csv_files.length ? files.csv_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无 CSV</div>';
      }
      if (document.getElementById('downloadDirs')) {
        downloadDirs.innerHTML = files.download_dirs.length ? files.download_dirs.map(f => `<div class="fileitem">${openButton(f)}<span class="filemeta">${f.count} 个 mp4</span></div>`).join('') : '<div class="empty">暂无下载目录</div>';
      }
      if (document.getElementById('analysisFiles')) {
        analysisFiles.innerHTML = files.analysis_files.length ? files.analysis_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无拆解结果</div>';
      }
      if (document.getElementById('scriptAnalysisFiles')) {
        scriptAnalysisFiles.innerHTML = files.analysis_files.length ? files.analysis_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无可选拆解结果</div>';
      }
      if (document.getElementById('scriptFiles')) {
        scriptFiles.innerHTML = files.script_files.length ? files.script_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无脚本产出结果</div>';
      }
      if (document.getElementById('adaptedScriptFiles')) {
        adaptedScriptFiles.innerHTML = files.adapted_script_files.length ? files.adapted_script_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无脚本适配结果</div>';
      }
      if (document.getElementById('adaptSourceScriptFiles')) {
        adaptSourceScriptFiles.innerHTML = files.script_files.length ? files.script_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无可选成品脚本</div>';
      }
      if (document.getElementById('assembledVideoFiles')) {
        assembledVideoFiles.innerHTML = files.assembled_video_files.length ? files.assembled_video_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无组合输出</div>';
      }
      if (document.getElementById('publishRecordFiles')) {
        publishRecordFiles.innerHTML = files.publish_record_files.length ? files.publish_record_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无发布记录</div>';
      }
      if (document.getElementById('metricsFiles')) {
        metricsFiles.innerHTML = files.metrics_files.length ? files.metrics_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无数据回收结果</div>';
      }
      if (document.getElementById('optimizationFiles')) {
        optimizationFiles.innerHTML = files.optimization_files.length ? files.optimization_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无脚本优化结果</div>';
      }
    }
    async function refresh() {
      const st = await api('/api/status');
      dot.className = 'dot' + (st.running ? ' running' : '');
      statusText.textContent = st.running ? `运行中：${st.task}` : (st.exit_code === null ? '未运行' : `已结束：${st.exit_code}`);
      const logText = (st.logs || []).join('\n');
      document.querySelectorAll('pre').forEach(el => {
        if (el) {
          el.textContent = logText;
          el.scrollTop = el.scrollHeight;
        }
      });
      renderFiles(st.files);
    }
    loadConfig().then(refresh);
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path in (
                "/",
                "/collect",
                "/product",
                "/analyze",
                "/script",
                "/adapt",
                "/assemble",
                "/publish",
                "/metrics",
                "/optimize",
            ):
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/config":
                self._json(200, config_payload())
            elif path == "/api/product-profile":
                self._json(200, load_config().get("product_profile", DEFAULT_PRODUCT_PROFILE))
            elif path == "/api/status":
                payload = JOBS.status()
                payload["files"] = file_listing()
                self._json(200, payload)
            elif path == "/api/open-path":
                raw_path = query.get("path", [""])[0]
                if not raw_path:
                    raise ValueError("缺少 path")
                open_local_path(raw_path)
                name = html.escape(Path(unquote(raw_path)).name)
                send_html(self, 200, f"<!doctype html><meta charset='utf-8'><title>已打开</title><body style='font:14px -apple-system,BlinkMacSystemFont,sans-serif;padding:24px'>已打开：{name}</body>")
            else:
                self._json(404, {"error": "Not found"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                self._json(200, save_config(self._read_json()))
            elif path == "/api/product-profile":
                self._json(200, save_product_profile(self._read_json()))
            elif path == "/api/teardown-defaults":
                self._json(200, save_teardown_defaults(self._read_json()))
            elif path == "/api/script-defaults":
                self._json(200, save_script_defaults(self._read_json()))
            elif path == "/api/content-workflow-defaults":
                self._json(200, save_content_workflow_defaults(self._read_json()))
            elif path == "/api/run/full":
                JOBS.start("一键采集", [sys.executable, "scripts/run_collection_pipeline.py"])
                self._json(200, {"ok": True})
            elif path == "/api/run/analyze":
                validate_analysis_input_path(load_config())
                JOBS.start("拆解视频", [sys.executable, "scripts/analyze_video_teardown_batch.py"])
                self._json(200, {"ok": True})
            elif path == "/api/run/script":
                validate_script_generation_input(load_config())
                JOBS.start("脚本产出", [sys.executable, "scripts/generate_product_script.py"])
                self._json(200, {"ok": True})
            elif path == "/api/run/adapt":
                JOBS.start("脚本适配", [sys.executable, "scripts/content_workflow_stage.py", "adapt"])
                self._json(200, {"ok": True})
            elif path == "/api/run/assemble":
                JOBS.start("片段组合", [sys.executable, "scripts/content_workflow_stage.py", "assemble"])
                self._json(200, {"ok": True})
            elif path == "/api/run/publish":
                JOBS.start("视频发布", [sys.executable, "scripts/content_workflow_stage.py", "publish"])
                self._json(200, {"ok": True})
            elif path == "/api/run/metrics":
                JOBS.start("数据回收", [sys.executable, "scripts/content_workflow_stage.py", "metrics"])
                self._json(200, {"ok": True})
            elif path == "/api/run/optimize":
                JOBS.start("脚本优化", [sys.executable, "scripts/content_workflow_stage.py", "optimize"])
                self._json(200, {"ok": True})
            elif path == "/api/open-path":
                payload = self._read_json()
                raw_path = payload.get("path", "")
                if not raw_path:
                    raise ValueError("缺少 path")
                open_local_path(raw_path)
                self._json(200, {"ok": True, "name": Path(unquote(raw_path)).name})
            elif path == "/api/choose-analysis-path":
                payload = self._read_json()
                selected = choose_analysis_path(payload.get("kind", "folder"))
                self._json(200, {"path": selected})
            elif path == "/api/choose-script-reference-path":
                selected = choose_script_reference_path()
                self._json(200, {"path": selected})
            elif path == "/api/choose-path":
                payload = self._read_json()
                selected = choose_local_path(payload.get("kind", "file"), payload.get("prompt", "选择文件"))
                self._json(200, {"path": selected})
            elif path == "/api/stop":
                self._json(200, {"stopped": JOBS.stop()})
            else:
                self._json(404, {"error": "Not found"})
        except Exception as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, *_):
        return


def main():
    STORAGE_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    ANALYSIS_DIR.mkdir(exist_ok=True)
    SCRIPT_OUTPUT_DIR.mkdir(exist_ok=True)
    ADAPTED_SCRIPT_DIR.mkdir(exist_ok=True)
    ASSEMBLED_VIDEO_DIR.mkdir(exist_ok=True)
    PUBLISH_RECORD_DIR.mkdir(exist_ok=True)
    METRICS_DIR.mkdir(exist_ok=True)
    SCRIPT_OPTIMIZATION_DIR.mkdir(exist_ok=True)
    KNOWLEDGE_BASE_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"科赛力量爆款收集专家已启动: {url}")
    if os.environ.get("KESAI_APP_NO_OPEN") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
