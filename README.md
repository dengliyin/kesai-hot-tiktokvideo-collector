# OPC 内容量化增长引擎

本地 Web 控制台，用于从产品信息出发，完成竞品爆款采集、视频拆解、脚本产出、脚本适配、片段组合、发布记录、数据回收和脚本优化的闭环。

## 启动

第一次使用时，可以从示例配置创建本地配置：

```bash
cp app_config.example.json app_config.json
```

`app_config.json` 会保存账号密码和任务参数，只保留在本机，不会提交到 Git。

```bash
./run_kesai_app.sh
```

启动后会自动打开：

```text
http://127.0.0.1:8765
```

## 使用流程

1. 先在「产品信息」页面保存你的产品资料。
2. 切换到「爆款采集」页面，填写账号、密码、关键词、国家/地区、三级类目、商品链接数量、每商品视频数量。
3. 点击「保存设置」。
4. 点击「一键采集」。
5. 在日志区域查看执行进度。默认启动后最小化浏览器窗口，你主要看日志即可。
6. 一键采集会先生成 CSV，再读取 CSV 的 `tiktok_video_url` 自动下载视频。
7. 切换到「视频拆解」页面，选择本地 MP4 或视频目录，把竞品爆款视频拆解成结构化脚本。
8. 切换到「脚本产出」页面，选择参考爆款拆解结果，结合「产品信息」生成自家产品带货脚本。
9. 切换到「脚本适配」页面，把成品脚本拆成适合 Veo/可灵等模型的 8 秒以内片段提示词，并生成首帧图描述。
10. 切换到「片段组合」页面，把生成好的片段组合成完整视频。
11. 切换到「视频发布」页面，生成发布计划/记录；自动发布接口后续接入。
12. 切换到「数据回收」页面，统一回收每条视频的播放、互动、点击、成交等数据。
13. 切换到「脚本优化」页面，根据同一脚本产出的所有视频数据做加权评估并产出优化建议。
14. 如果遇到验证码或滑块，勾选「显示浏览器窗口」后重新运行，在弹出的浏览器里手动完成验证。

## 产品信息

同一个本地入口里有独立的「产品信息」页面，用来保存你的产品资料，后续可以和竞品爆款视频拆解结果一起用于仿写带货脚本。

产品信息只保存在本地 `app_config.json` 的 `product_profile` 字段，不会提交到 Git。字段结构按产品资料 Markdown 调整，包括基础识别、定价策略、TOP 3 核心卖点、目标人群 × 痛点矩阵、核心痛点与转化话术、TikTok 营销推广切入点、市场关键词参考、适配素材类型建议和补充备注。

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

## 视频拆解

在同一个本地入口切换到「视频拆解」页面，可以保存中转 API Key、切换模型、修改拆解提示词，并点击「拆解视频」分析 MP4。

「拆解视频路径」可以手动填写，也可以点击「选择目录」批量拆解一个目录，或点击「选择视频」单独拆解一个 MP4。视频拆解和爆款采集互相独立，路径不能为空，也不会自动使用采集下载目录。

视频拆解会同时读取本地「爆款内容知识库」文件：

```text
knowledge_base/hot_content_knowledge_base.md
```

这份文件用于保存爆款内容方法论、素材类型、原生感规则、转化逻辑和判断标准，只保存在本机，不会提交到 Git。它同时服务于“竞品视频拆解”和“脚本产出改写”。旧版 `knowledge_base/video_teardown_knowledge_base.md` 会被兼容读取，但新配置统一使用 `hot_content_knowledge_base.md`。

点击「保存设置」后，这些字段只保存在本地 `app_config.json`，不要提交到 Git：

```json
{
  "modelmesh_api_key": "",
  "modelmesh_base_url": "https://router.shengsuanyun.com/api",
  "video_analysis_model": "google/gemini-3-flash",
  "video_analysis_prompt": "",
  "video_teardown_knowledge_base_path": "knowledge_base/hot_content_knowledge_base.md",
  "video_analysis_max_output_tokens": 32768,
  "analysis_input_path": ""
}
```

按已保存的 `analysis_input_path` 批量拆解：

```bash
python3 scripts/analyze_video_teardown_batch.py
```

对单个 MP4 做最小测试：

```bash
python3 scripts/analyze_video_teardown.py /path/to/video.mp4
```

结果会输出到本地 `analysis/`，该目录不会提交到 Git。`analysis_input_path` 是目录时会拆解目录下全部 MP4，是单个 MP4 文件时只拆解该视频。

## 脚本产出

在同一个本地入口切换到「脚本产出」页面，核心输入是四类：

- 改写提示词：规定怎么复刻和改写。
- 参考爆款拆解结果：来自 `analysis/` 的 Markdown，提供具体爆款案例；素材框架和案例节奏会从这个拆解结果中自动提取，不需要手动填写。
- 产品信息：来自「产品信息」页保存的 `product_profile`。
- 爆款内容知识库：与视频拆解共用 `knowledge_base/hot_content_knowledge_base.md`，提供长期方法论和素材框架。

系统会把这四类输入合并，把竞品爆款视频的逻辑和情绪节奏改写成适合自家产品的新带货脚本。

改写提示词默认保存在本地文件：

```text
knowledge_base/script_generation_prompt.md
```

这份提示词只保存在本机，不会提交到 Git。页面里修改并点击「保存设置」后，会更新这份本地文件。爆款内容知识库在视频拆解页和脚本产出页只显示本地路径，需要调整正文时点击「打开文件」后在本地文件里编辑。

命令行生成脚本：

```bash
python3 scripts/generate_product_script.py
```

结果会输出到本地 `script_outputs/`，该目录不会提交到 Git。

## 内容分发闭环

新增的五个页面先提供可运行框架，方便逐步接入真实模型和平台接口：

- 「脚本适配」读取 `script_outputs/` 中的成品脚本，输出 `adapted_scripts/`，结构包含每个视频片段的时长上限、视频生成提示词草案和首帧图描述。
- 「片段组合」读取一个视频片段目录，输出 `assembled_videos/`。如果本机有 `ffmpeg` 且目录内有 mp4/mov，会尝试无转码合并；否则输出组合清单。
- 「视频发布」输出 `publish_records/`，当前是发布计划/记录框架，不会自动登录或发布 TikTok。
- 「数据回收」读取平台导出的 CSV 或手动数据，输出 `metrics/`，会先做数值字段汇总。
- 「脚本优化」读取原脚本和数据回收结果，输出 `script_optimizations/`，先形成加权评估和优化建议框架。

命令行也可以分别运行：

```bash
python3 scripts/content_workflow_stage.py adapt
python3 scripts/content_workflow_stage.py assemble
python3 scripts/content_workflow_stage.py publish
python3 scripts/content_workflow_stage.py metrics
python3 scripts/content_workflow_stage.py optimize
```

这些输出目录都只保存在本地，不会提交到 Git。
