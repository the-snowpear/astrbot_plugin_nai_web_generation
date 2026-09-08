# 贡献指南 (Contributing Guide)

感谢您关注并考虑为 `astrbot_plugin_NAI_Web_Generation` 做出贡献！无论是提交 Issue、建议新功能还是提交 Pull Request，我们都非常欢迎。

---

## 目录
- [代码行为准则](#代码行为准则)
- [开发环境准备](#开发环境准备)
- [代码规范与风格](#代码规范与风格)
- [运行测试](#运行测试)
- [提交 Pull Request](#提交-pull-request)

---

## 代码行为准则

请保持友好、尊重与包容的社区交流氛围。我们鼓励具有建设性的讨论和反馈。

---

## 开发环境准备

1. **Fork 并 Clone 仓库**：
   ```bash
   git clone https://github.com/the-snowpear/astrbot_plugin_NAI_Web_Generation.git
   cd astrbot_plugin_NAI_Web_Generation
   ```

2. **安装依赖**：
   建议在虚拟环境中安装依赖：
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

---

## 代码规范与风格

- **PEP 8**：遵循标准 Python PEP 8 代码风格规范。
- **类型提示 (Type Hints)**：新增函数与方法请尽可能补充完整的类型注解。
- **Docstrings**：保持清晰简洁的函数与类说明文档。
- **结构规范**：保持标准 AstrBot 单层插件结构，入口为根目录的 `main.py` 与 `metadata.yaml`。

---

## 运行测试

在提交修改之前，请确保所有自动化回归测试通过：

```bash
python -m unittest discover tests
```

如果添加了新功能或修复了 Bug，请在 `tests/` 目录下添加对应的单元测试覆盖。

---

## 提交 Pull Request

1. 从 `main` 分支切出新的功能分支：
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. 提交您的修改，编写清晰明确的 Commit Message（推荐遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范，如 `feat: ...`, `fix: ...`, `docs: ...`）。
3. 推送到您的远程分支：
   ```bash
   git push origin feature/your-feature-name
   ```
4. 在 GitHub 上发起 Pull Request，详细描述修改的内容与动机。
