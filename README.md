# 科赛力量爆款收集专家

本地 Web 控制台，用于按 FastMoss 商品搜索条件采集 TikTok 商品关联视频数据，并通过达人精灵下载无水印视频。

## 启动

第一次使用时，可以从示例配置创建本地配置：

```bash
cp fastmoss_config.example.json fastmoss_config.json
```

`fastmoss_config.json` 会保存账号密码和任务参数，只保留在本机，不会提交到 Git。

```bash
./run_fastmoss_app.sh
```

启动后会自动打开：

```text
http://127.0.0.1:8765
```

## 使用流程

1. 在页面里填写账号、密码、关键词、国家/地区、三级类目、商品链接数量、每商品视频数量。
2. 点击「保存参数」。
3. 点击「一键采集」。
4. 在日志区域查看执行进度。默认启动后最小化浏览器窗口，你主要看日志即可。
5. 一键采集会先生成 CSV，再读取 CSV 的 `tiktok_video_url` 自动下载视频。
6. 如果遇到验证码或滑块，勾选「显示浏览器窗口」后重新运行，在弹出的浏览器里手动完成验证。
7. CSV 会出现在 `storage/`，视频会出现在 `downloads/<CSV文件名>/`。

## 输出命名

CSV 文件名格式：

```text
关键词_国家_完整三级类目_年月日_商品链接数量_视频URL数量.csv
```

视频文件名格式：

```text
TikTok视频ID.mp4
```

例如：

```text
7622175051634314497.mp4
```

## Gemini 视频拆解测试

页面里已经有「视频拆解默认设置」区域，可以保存中转 API Key、切换模型、修改拆解提示词，并点击「拆解视频」分析 MP4。

「拆解视频路径」可以手动填写，也可以点击「选择目录」批量拆解一个目录，或点击「选择视频」单独拆解一个 MP4。留空时默认分析最新下载目录里的 MP4。

点击「保存默认设置」后，这些字段只保存在本地 `fastmoss_config.json`，不要提交到 Git：

```json
{
  "modelmesh_api_key": "",
  "modelmesh_base_url": "https://router.shengsuanyun.com/api",
  "video_analysis_model": "google/gemini-3-flash",
  "video_analysis_prompt": "",
  "analysis_input_path": ""
}
```

批量拆解最新下载目录：

```bash
python3 scripts/gemini_video_teardown_batch.py
```

对单个 MP4 做最小测试：

```bash
python3 scripts/gemini_video_teardown_test.py /path/to/video.mp4
```

结果会输出到本地 `analysis/`，该目录不会提交到 Git。`analysis_input_path` 是目录时会拆解目录下全部 MP4，是单个 MP4 文件时只拆解该视频。
