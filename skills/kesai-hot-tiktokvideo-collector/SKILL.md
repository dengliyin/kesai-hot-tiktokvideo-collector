---
name: kesai-hot-tiktokvideo-collector
description: Run and maintain the local "科赛力量爆款收集专家" app for FastMoss TikTok product/video collection, Kolsprite video downloads, and Gemini/ModelMesh video teardown tests. Use when the user asks to collect FastMoss product-linked TikTok video data, export TikTok video URLs, download videos from collected URLs, analyze downloaded TikTok videos into scripts, adjust the app workflow, update saved task parameters, or troubleshoot this specific collector.
---

# 科赛力量爆款收集专家

## Overview

Use the local collector project to search FastMoss products by keyword, country/region, and a three-level category path, collect product-linked video metrics and TikTok URLs, download the corresponding no-watermark MP4 files through Kolsprite, and test Gemini-based teardown of downloaded videos.

The canonical project root on this machine is:

```text
/Users/kesai1/Documents/New project
```

If the current workspace contains `fastmoss_app.py`, prefer the current workspace as the project root.

## Required Parameters

Collect or confirm these values before running a new task:

- FastMoss phone number and password.
- Keyword value provided by the user at runtime. Do not store real keyword examples in committed files.
- Country/region label exactly as FastMoss displays it, such as `马来西亚`.
- Three-level category path, separated with `>`, such as `美妆个护 > 头部护理与造型 > 染发用品`.
- Product link count.
- Video count per product.

The app stores parameters in `fastmoss_config.json`. This file contains local credentials and must not be committed or printed back verbatim.

## Main Workflow

1. Open or update `fastmoss_config.json` with the requested parameters. Use `fastmoss_config.example.json` as the schema if the config file does not exist.
2. Keep `show_browser` as `false` by default. The automation opens Chrome for Testing and minimizes it so the user mainly watches logs.
3. Run the local web app when the user wants a visible control panel:

```bash
./run_fastmoss_app.sh
```

4. The app opens at:

```text
http://127.0.0.1:8765
```

5. For a direct command-line run, execute the full pipeline:

```bash
python3 scripts/full_pipeline.py
```

The full pipeline first runs `scripts/fastmoss_test_video_urls.py`, then `scripts/kolsprite_download_videos.py`.

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

- Reads `modelmesh_api_key`, `modelmesh_base_url`, `video_analysis_model`, and `video_analysis_prompt` from local `fastmoss_config.json` or environment variables.
- Calls the Shengsuanyun/ModelMesh Gemini-compatible endpoint with a local MP4 as base64 inline video.
- Uses `google/gemini-3-flash` by default.
- Writes Markdown and raw JSON results to local `analysis/`.

Run a single-video minimal test with:

```bash
python3 scripts/gemini_video_teardown_test.py /path/to/video.mp4
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

- Never commit `fastmoss_config.json`, `storage/`, `browser-profile/`, `downloads/`, `app.log`, or generated MP4/CSV files.
- Never commit `analysis/`, model API keys, or the user's proprietary teardown prompt.
- Never commit real task keywords in examples, defaults, docs, or skill text. Use an empty value or a generic placeholder.
- Do not print the saved FastMoss password in final responses or logs beyond what the app already masks in its UI.
- Prefer the app and existing scripts over ad hoc browser automation unless debugging a selector failure.
- When changing the app, keep the user-facing title as `科赛力量爆款收集专家`.
