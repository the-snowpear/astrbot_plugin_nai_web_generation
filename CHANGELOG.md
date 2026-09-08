# 更新日志 (CHANGELOG)

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/) 语义化版本规范。

---

## [v1.0.8] - 2026-09-08

### 结构优化 (Refactor)
- **标准 AstrBot 插件单层重构**：将原嵌套子目录提取至项目根目录，完美符合 AstrBot 官方插件加载机制。
- **模块导入鲁棒性增强**：在 `main.py` 和 `nai_client.py` 增加相对/绝对导入双重容错，兼顾 AstrBot 运行时包加载与外部自动化测试。
- **开源规范套件落地**：引入 MIT 许可证、贡献指南、变更日志、项目专属 Logo（`logo.png`）及规范的 `.gitignore` 配置。

---

## [v1.0.7] - 2026-07-28

### 新增功能 (Features)
- **紧凑消息模式 (`compact`)**：支持仅输出「开始提示」、「图片展示」与可选的「参数详情」；
- **合并转发支持**：紧凑模式下针对 OneBot v11 群聊发送合并转发消息，其他消息平台自动无缝降级为普通详情。

### 修复与优化 (Fixes & Improvements)
- **画风前缀污染隔离**：重构画风和 artist 前缀解析逻辑，未指定或非法画风严格隔离，防止前缀污染后续生成。
- **原始空格保留**：指令解析保留自然语言及 NAI 权重括号间的连续空格，避免提示词解析截断。

---

## [v1.0.5] - 2026-07-28

### 新增功能 (Features)
- **LLM Function Calling 自动生图 (`nai_generate_image`)**：支持大模型意图识别自动触发文生图，实现免斜杠命令自然对话生图。

### 修复与优化 (Fixes & Improvements)
- 修复 `default_style` 为 `none` 时的校验异常，支持纯提示词直出。
- 修复超长指令解析被 AstrBot 命令解析器阶段截断的问题。

---

## [v1.0.0] - 2026-07-20

### 初始发布 (Initial Release)
- 基于 [nai.sta1n.cn](https://nai.sta1n.cn)（Nai2API）网关的 NovelAI 文生图集成。
- 支持 `/nai` 默认直出、`/nai2` LLM 中文直译提取参数、`/nai3` 创作型提示词生成。
- 内置 `doc712` 与 `website` 双套画风包切换。
- 支持 Job 异步创建与轮询出图机制。
