---
name: kesai-hot-tiktokvideo-collector
description: Run and maintain the local "科赛力量爆款收集专家" app for product context storage, FastMoss TikTok product/video collection, Kolsprite video downloads, Gemini/ModelMesh video teardown, product script generation, script adaptation, clip assembly, publishing records, metrics recovery, and script optimization. Use when the user asks to collect FastMoss product-linked TikTok video data, export TikTok video URLs, download videos from collected URLs, analyze downloaded TikTok videos into scripts, generate product sales scripts from teardown results and product information, adapt scripts for video generation models, combine generated clips, prepare TikTok publishing records, recover video metrics, optimize scripts from performance data, adjust the app workflow, update saved task parameters, or troubleshoot this specific collector.
---

# 科赛力量爆款收集专家

## Overview

Use the local collector project to store product context, search FastMoss products by keyword, country/region, and a three-level category path, collect product-linked video metrics and TikTok URLs, download the corresponding no-watermark MP4 files through Kolsprite, tear down downloaded videos with Gemini/ModelMesh, generate new product sales scripts from competitor teardown results plus the saved product profile, adapt scripts for video generation models, assemble generated clips, record publishing plans, recover performance metrics, and optimize scripts from data.

The canonical project root on this machine is:

```text
/Users/kesai1/Documents/New project
```

If the current workspace contains `kesai_app.py`, prefer the current workspace as the project root.

## Required Parameters

Collect or confirm these values before running a new task:

- FastMoss phone number and password.
- Keyword value provided by the user at runtime. Do not store real keyword examples in committed files.
- Country/region label exactly as FastMoss displays it, such as `马来西亚`.
- Three-level category path, separated with `>`, such as `美妆个护 > 头部护理与造型 > 染发用品`.
- Product link count.
- Video count per product.
- For script generation: a competitor video teardown Markdown file, target country/region, target language, total duration, hook duration, and optional emotion/framework/reference-case notes.
- For the content distribution loop: an output script, target video generation model, generated clip folder, publishing account alias/caption/tags, exported metrics CSV or manual metrics, and the script to optimize.

The app stores parameters in `app_config.json`. This file contains local credentials and must not be committed or printed back verbatim.

## Main Workflow

1. Open or update `app_config.json` with the requested parameters. Use `app_config.example.json` as the schema if the config file does not exist.
2. Keep `show_browser` as `false` by default. The automation opens Chrome for Testing and minimizes it so the user mainly watches logs.
3. Run the local web app when the user wants a visible control panel:

```bash
./run_kesai_app.sh
```

4. The app opens at:

```text
http://127.0.0.1:8765
```

5. The app has separate pages under the same local entry in workflow order: `/product`, `/collect`, `/analyze`, `/script`, `/adapt`, `/assemble`, `/publish`, `/metrics`, and `/optimize`.
6. For a direct command-line run, execute the full pipeline:

```bash
python3 scripts/run_collection_pipeline.py
```

The full pipeline first runs `scripts/collect_fastmoss_product_videos.py`, then `scripts/download_tiktok_videos_kolsprite.py`.

## What The Collector Does

The FastMoss collection phase:

- Checks whether the program is already logged in.
- Logs in automatically when the login state has expired.
- Closes the entry popup on the FastMoss dashboard.
- Searches by keyword.
- Selects country/region.
- Selects the first-, second-, and third-level category; verify the selected condition appears in the FastMoss "已选条件" area.
- Opens the top product detail pages according to `product_limit`.
- Enters `商品关联视频`.
- Collects up to `videos_per_product` videos per product, paging every 5 rows.
- Records video title, creator name, 28-day sales, 28-day GMV, 28-day ad spend, 28-day ROAS, views, likes, comments, interaction rate, publish time, and `tiktok_video_url`.

The download phase:

- Reads the newest CSV in `storage/` that contains `tiktok_video_url`.
- Opens `https://dl.kolsprite.com/tools/video-download`.
- Submits each TikTok URL.
- Clicks the high-quality no-watermark MP4 download option.
- Saves each video using only the TikTok video ID, for example `7622175051634314497.mp4`.

The Gemini teardown test phase:

- Reads `modelmesh_api_key`, `modelmesh_base_url`, `video_analysis_model`, `analysis_input_path`, `video_analysis_prompt`, and the shared content knowledge base path from local `app_config.json` or environment variables.
- Calls the Shengsuanyun/ModelMesh Gemini-compatible endpoint with a local MP4 as base64 inline video.
- Uses `google/gemini-3-flash` by default.
- Writes Markdown and raw JSON results to local `analysis/`.
- The Web UI has a separate "视频拆解" page for editing and locally saving the API key, model, teardown prompt, shared hot-content knowledge base path, and a manual video path. The path can be a directory of MP4 files or a single MP4 file; directories are analyzed in full, single files are analyzed alone, and the path is required. The teardown page does not automatically use collection download folders. The UI only shows the shared knowledge base path; edit the knowledge base text by opening the local file.
- The first local shared content knowledge base is stored at `knowledge_base/hot_content_knowledge_base.md`. It is local-only and ignored by Git. Use it for competitor/video teardown methodology and script rewriting methodology; product profile context still lives separately under `product_profile`. Legacy local files named `knowledge_base/video_teardown_knowledge_base.md` are read as a fallback only.

The product profile phase:

- The Web UI has a separate "产品信息" page for saving the user's product context locally.
- Product profile data is stored under `product_profile` in `app_config.json`.
- Product profile fields follow the product Markdown structure: basic identification, pricing strategy, top 3 selling points, audience x pain matrix, pain/conversion talk tracks, TikTok marketing angles, market keywords, material type suggestions, and notes.
- Treat product profile content as local business context. Do not commit real product details unless the user explicitly provides sanitized examples for documentation.

The script generation phase:

- The Web UI has a separate "脚本产出" page for turning four inputs into a new product sales script: rewrite prompt, competitor teardown Markdown, saved product profile, and shared content knowledge base.
- It reads `product_profile`, `video_teardown_knowledge_base_path`, `script_generation_prompt_path`, `script_reference_analysis_path`, `script_country`, `script_target_language`, `script_total_duration`, `script_hook_duration`, `script_audio_emotion`, `script_material_framework`, and `script_reference_case` from local `app_config.json`.
- The default rewrite prompt is stored at `knowledge_base/script_generation_prompt.md`. The shared content knowledge base is stored at `knowledge_base/hot_content_knowledge_base.md`. Both are local-only and ignored by Git.
- Results are written to local `script_outputs/`.

The content distribution loop:

- `/adapt` turns a finished script into video-model-friendly segment prompts and first-frame image descriptions. Results are written to `adapted_scripts/`.
- `/assemble` combines generated clip files into a full video when `ffmpeg` is available, or writes an assembly manifest. Results are written to `assembled_videos/`.
- `/publish` creates publishing plans/records for TikTok accounts. It does not auto-publish until an account authorization method is explicitly added. Records are written to `publish_records/`.
- `/metrics` recovers video performance data from CSV or manual input, then writes normalized summaries to `metrics/`.
- `/optimize` uses the source script plus recovered metrics to create weighted evaluation and optimization suggestions. Results are written to `script_optimizations/`.
- These five stages currently provide runnable scaffolds through `scripts/content_workflow_stage.py`; treat them as framework entry points until the user asks to wire a specific video generation, publishing, or analytics provider.

Run a single-video minimal test with:

```bash
python3 scripts/analyze_video_teardown.py /path/to/video.mp4
```

Run batch teardown for the saved `analysis_input_path` with:

```bash
python3 scripts/analyze_video_teardown_batch.py
```

Generate a product script from the saved script settings with:

```bash
python3 scripts/generate_product_script.py
```

Run a content distribution scaffold stage with:

```bash
python3 scripts/content_workflow_stage.py adapt
python3 scripts/content_workflow_stage.py assemble
python3 scripts/content_workflow_stage.py publish
python3 scripts/content_workflow_stage.py metrics
python3 scripts/content_workflow_stage.py optimize
```

## Outputs

CSV files are written to `storage/`.

CSV filename format:

```text
关键词_国家_完整三级类目_年月日_商品链接数量_视频URL数量.csv
```

Downloaded videos are written to `downloads/<CSV文件名>/`.

Video filename format:

```text
TikTok视频ID.mp4
```

## Troubleshooting

- If FastMoss shows a CAPTCHA, slider, security block, or the login page cannot be detected, set `show_browser` to `true`, rerun, and ask the user to complete the visible browser step manually.
- If category selection seems wrong, inspect the log for the confirmed category string. The third-level category must be clicked, not only hovered.
- If login fails in minimized mode, rerun with the browser visible once so the persistent browser profile can refresh its session.
- If the downloader skips a video, check whether an MP4 with the same TikTok video ID already exists in the target download directory.

## Safety Rules

- Never commit `app_config.json`, `fastmoss_config.json`, `storage/`, `browser-profile/`, `downloads/`, `app.log`, or generated MP4/CSV files.
- Never commit `analysis/`, `knowledge_base/`, `script_outputs/`, `adapted_scripts/`, `assembled_videos/`, `publish_records/`, `metrics/`, `script_optimizations/`, model API keys, or the user's proprietary teardown/script prompts, teardown knowledge base, product profile, generated scripts, generated clips, publishing records, or performance data.
- Never commit real task keywords in examples, defaults, docs, or skill text. Use an empty value or a generic placeholder.
- Do not print the saved FastMoss password in final responses or logs beyond what the app already masks in its UI.
- Prefer the app and existing scripts over ad hoc browser automation unless debugging a selector failure.
- When changing the app, keep the user-facing title as `科赛力量爆款收集专家`.
