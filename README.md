# 🎙️基于LLM的智能语音日记助手

> 一个基于 Python 的全流程 AI 语音日记应用。集成 **ASR 语音转写** 与 **LLM 大模型深度分析**，将碎片化的语音记录转化为结构化的心理分析报告。

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![AI](https://img.shields.io/badge/AI-DeepSeek%20%2F%20ERNIE-green)
![ASR](https://img.shields.io/badge/ASR-iFlyTek-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## 📖 项目简介 (Introduction)

通过集成 **科大讯飞 (iFlyTek)** 的实时语音转写能力和 **DeepSeek / 百度文心一言** 的深度推理能力，用户只需口述日记，程序即可自动完成“录音 -> 转写 -> 情感分析 -> 结构化报告生成”的全流程。

**核心价值：** 利用 Prompt Engineering（提示工程）让 AI 扮演专业心理分析师，为用户提供情绪洞察与生活建议。

## ✨ 核心功能 (Key Features)

- **🎙️ 实时语音采集与流式处理**
  - [cite_start]基于 `PyAudio` 实现多麦克风设备自动检测与实时录音 [cite: 9, 177]。
  - 录音过程可视化，支持时长实时统计。

- **⚡ 高效 ASR 语音转写**
  - [cite_start]集成 **科大讯飞 (iFlyTek)** WebSocket API [cite: 14, 243]。
  - 实现了音频数据的流式上传与结果实时回显，支持长语音精准转写。

- **🧠 双引擎 AI 深度分析**
  - [cite_start]**多模型支持：** 内置 **DeepSeek-Chat** 与 **百度文心一言 (ERNIE)** 双大模型接口，用户可自由切换 [cite: 22, 302]。
  - [cite_start]**异步调用架构：** 基于 `threading` + `requests` 实现异步网络请求，确保 AI 思考期间 GUI 界面流畅无卡顿 [cite: 700]。

- **🎨 结构化 Prompt 系统**
  - [cite_start]内置精心设计的 System Prompt（系统提示词），指导 AI 输出包含“情感倾向”、“核心关键词”、“主题摘要”及“深度建议”的结构化内容 [cite: 25, 168]。
  - [cite_start]支持用户自定义 Prompt，灵活调整 AI 的分析人格与输出风格 [cite: 23]。

- **📝 Markdown 报告导出**
  - [cite_start]分析结果自动渲染为 Markdown 格式，支持一键导出 `.md` 文件，便于归档与二次编辑 [cite: 38, 720]。

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术方案 | 说明 |
| :--- | :--- | :--- |
| **编程语言** | Python 3.x | 核心逻辑实现 |
| **GUI 框架** | Tkinter + ttk | [cite_start]现代化图形界面，自定义 Style 样式 [cite: 30] |
| **语音识别 (ASR)** | **WebSocket** | [cite_start]接入科大讯飞在线听写 API [cite: 14] |
| **大模型 (LLM)** | **REST API** | [cite_start]接入 DeepSeek / 文心一言 [cite: 20] |
| **并发处理** | **Threading** | [cite_start]实现网络请求的异步非阻塞调用，优化 UX [cite: 136] |
| **音频处理** | PyAudio + Wave | [cite_start]音频流录制与 WAV 格式封装 [cite: 7, 138] |
