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
CONFIG_PATH = ROOT / "fastmoss_config.json"
STORAGE_DIR = ROOT / "storage"
DOWNLOAD_DIR = ROOT / "downloads"
ANALYSIS_DIR = ROOT / "analysis"
HOST = "127.0.0.1"
PORT = int(os.environ.get("FASTMOSS_APP_PORT", "8765"))

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
    "video_analysis_max_output_tokens": 32768,
    "analysis_input_path": "",
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
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            config = json.load(f)
        merged = DEFAULT_CONFIG | config
        return merged
    return DEFAULT_CONFIG.copy()


def save_config(config):
    config = DEFAULT_CONFIG | config
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
    config["video_analysis_max_output_tokens"] = int(config.get("video_analysis_max_output_tokens", 32768))
    config["analysis_input_path"] = str(config.get("analysis_input_path", "")).strip()
    config.pop("analysis_video_limit", None)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if "analysis_input_path" in payload:
        config["analysis_input_path"] = str(payload.get("analysis_input_path", config.get("analysis_input_path", ""))).strip()
    config["video_analysis_max_output_tokens"] = int(config.get("video_analysis_max_output_tokens", 32768))
    config.pop("analysis_video_limit", None)
    return save_config(config)


def file_listing():
    STORAGE_DIR.mkdir(exist_ok=True)
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    ANALYSIS_DIR.mkdir(exist_ok=True)
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
    return {"csv_files": csv_files, "download_dirs": download_dirs, "analysis_files": analysis_files}


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
    header { position:sticky; top:0; z-index:2; height:58px; display:flex; align-items:center; justify-content:space-between; padding:0 28px; background:rgba(255,255,255,.78); border-bottom:1px solid rgba(0,0,0,.08); backdrop-filter:saturate(180%) blur(18px); }
    h1 { margin:0; font-size:18px; font-weight:700; letter-spacing:0; }
    main { max-width:1360px; margin:24px auto 40px; padding:0 22px; display:grid; grid-template-columns: 440px minmax(0,1fr); gap:20px; align-items:start; }
    section { background:var(--panel); border:1px solid rgba(0,0,0,.08); border-radius:8px; padding:20px; box-shadow:var(--shadow); }
    h2 { font-size:16px; line-height:1.25; margin:0 0 16px; font-weight:700; }
    label { display:block; margin:13px 0 6px; color:#424245; font-size:12px; font-weight:700; }
    input, select, textarea { width:100%; border:1px solid #d2d2d7; border-radius:8px; padding:10px 12px; font:inherit; outline:none; background:var(--field); color:var(--text); transition:border-color .16s ease, box-shadow .16s ease, background .16s ease; }
    input, select { min-height:42px; }
    input:focus, select:focus, textarea:focus { border-color:var(--accent); background:#fff; box-shadow:0 0 0 4px rgba(0,113,227,.12); }
    textarea { min-height:78px; resize:vertical; }
    textarea.prompt { min-height:260px; font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif; }
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
    .pathrow { display:flex; gap:8px; align-items:center; }
    .pathrow input { min-width:0; }
    .pathrow button { flex:0 0 auto; }
    .toast { position:fixed; top:72px; right:24px; z-index:10; max-width:360px; padding:12px 14px; border-radius:8px; background:rgba(29,29,31,.92); color:#fff; box-shadow:0 14px 36px rgba(0,0,0,.18); opacity:0; pointer-events:none; transform:translateY(-8px); transition:opacity .18s ease, transform .18s ease; }
    .toast.show { opacity:1; transform:translateY(0); }
    .toast.error { background:rgba(215,0,21,.94); }
    @media (max-width:1100px) { .files { grid-template-columns:1fr; } }
    @media (max-width:900px) { main { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>科赛力量爆款收集专家</h1>
    <div class="status"><span id="dot" class="dot"></span><span id="statusText">未运行</span></div>
  </header>
  <div id="toast" class="toast"></div>
  <main>
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
      <div class="divider"></div>
      <div class="sectionhead">
        <h2>视频拆解默认设置</h2>
        <span class="filemeta">本地保存</span>
      </div>
      <label>ModelMesh API Key</label>
      <input id="modelmesh_api_key" type="password" autocomplete="off" placeholder="只保存在本地 fastmoss_config.json" />
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
      <label>拆解视频路径</label>
      <div class="pathrow">
        <input id="analysis_input_path" placeholder="留空时自动使用最新下载目录" />
        <button onclick="chooseAnalysisPath('folder')">选择目录</button>
        <button onclick="chooseAnalysisPath('file')">选择视频</button>
      </div>
      <label>爆款视频拆解提示词</label>
      <textarea id="video_analysis_prompt" class="prompt" placeholder="粘贴或修改你的爆款视频拆解提示词；留空时使用最小测试提示词"></textarea>
      <div class="buttons">
        <button class="primary" onclick="saveTeardownDefaults()">保存默认设置</button>
        <button class="blue" onclick="startTask('analyze')">拆解视频</button>
      </div>
      <p class="muted">选择目录时会拆解目录下全部 MP4；选择单个视频时只拆解该视频。API Key 和提示词只保存在本地配置文件，不会提交到 GitHub。</p>
    </section>
    <section>
      <h2>运行日志</h2>
      <pre id="logs"></pre>
      <div class="files">
        <div class="filebox">
          <h2>CSV 输出</h2>
          <div id="csvFiles" class="muted">加载中...</div>
        </div>
        <div class="filebox">
          <h2>视频下载目录</h2>
          <div id="downloadDirs" class="muted">加载中...</div>
        </div>
        <div class="filebox">
          <h2>视频拆解结果</h2>
          <div id="analysisFiles" class="muted">加载中...</div>
        </div>
      </div>
    </section>
  </main>
  <script>
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
      analysis_input_path.value = cfg.analysis_input_path || '';
      video_analysis_prompt.value = cfg.video_analysis_prompt || '';
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
        show_browser: show_browser.checked,
        modelmesh_api_key: modelmesh_api_key.value.trim(),
        modelmesh_base_url: modelmesh_base_url.value.trim(),
        video_analysis_model: video_analysis_model.value,
        analysis_input_path: analysis_input_path.value.trim(),
        video_analysis_prompt: video_analysis_prompt.value
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
        analysis_input_path: analysis_input_path.value.trim(),
        video_analysis_prompt: video_analysis_prompt.value
      };
      await api('/api/teardown-defaults', {method:'POST', body:JSON.stringify(payload)});
      await refresh();
      if (!silent) alert('视频拆解默认设置已保存到本地');
    }
    async function startTask(task) {
      if (task === 'analyze') {
        await saveTeardownDefaults(true);
      } else {
        await saveConfig(true);
      }
      await api('/api/run/' + task, {method:'POST', body:'{}'});
      await refresh();
    }
    async function stopTask() {
      await api('/api/stop', {method:'POST', body:'{}'});
      await refresh();
    }
    async function chooseAnalysisPath(kind) {
      const res = await api('/api/choose-analysis-path', {method:'POST', body:JSON.stringify({kind})});
      analysis_input_path.value = res.path || '';
      await saveConfig(true);
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
      csvFiles.innerHTML = files.csv_files.length ? files.csv_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无 CSV</div>';
      downloadDirs.innerHTML = files.download_dirs.length ? files.download_dirs.map(f => `<div class="fileitem">${openButton(f)}<span class="filemeta">${f.count} 个 mp4</span></div>`).join('') : '<div class="empty">暂无下载目录</div>';
      analysisFiles.innerHTML = files.analysis_files.length ? files.analysis_files.map(f => `<div class="fileitem">${openButton(f)}</div>`).join('') : '<div class="empty">暂无拆解结果</div>';
    }
    async function refresh() {
      const st = await api('/api/status');
      dot.className = 'dot' + (st.running ? ' running' : '');
      statusText.textContent = st.running ? `运行中：${st.task}` : (st.exit_code === null ? '未运行' : `已结束：${st.exit_code}`);
      logs.textContent = (st.logs || []).join('\n');
      logs.scrollTop = logs.scrollHeight;
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
            if path == "/":
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/config":
                self._json(200, load_config())
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
            elif path == "/api/teardown-defaults":
                self._json(200, save_teardown_defaults(self._read_json()))
            elif path == "/api/run/full":
                JOBS.start("一键采集", [sys.executable, "scripts/full_pipeline.py"])
                self._json(200, {"ok": True})
            elif path == "/api/run/analyze":
                JOBS.start("拆解视频", [sys.executable, "scripts/gemini_video_teardown_batch.py"])
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
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"科赛力量爆款收集专家已启动: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
