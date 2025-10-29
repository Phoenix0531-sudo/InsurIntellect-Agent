# Windows 下安装与配置 Tesseract OCR

本文档帮助你在 Windows 安装 Tesseract，并在本项目中启用 OCR 回退，解决 “tesseract is not installed or it's not in your PATH” 报错。

## 1. 安装 Tesseract

- 前往 Tesseract Windows 安装包（推荐 UB Mannheim 构建，带多语言）：
  - https://github.com/UB-Mannheim/tesseract/wiki
- 下载 `tesseract-ocr-w64-setup-<version>.exe`（64 位）。
- 安装时建议保留默认路径：`C:\Program Files\Tesseract-OCR`。
- 在安装向导中勾选中文语言包（`chi_sim` 简体中文）和英文（`eng`）。

如果安装时未选择语言包，可在安装完成后手动添加：

1) 下载中文训练数据 `chi_sim.traineddata`：
- 训练数据仓库：https://github.com/tesseract-ocr/tessdata
- 将 `chi_sim.traineddata` 放入 `C:\Program Files\Tesseract-OCR\tessdata\`。

## 2. 配置环境变量/项目变量

项目支持两种方式告知 Tesseract 路径：

- 在 `.env` 文件中设置：
  ```env
  TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
  OCR_LANG=chi_sim+eng
  ```
- 或在 `app/core/ingestion_config.yml` 中设置：
  ```yaml
  general:
    ocr:
      tesseract_cmd: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
      lang: "chi_sim+eng"
  ```

本项目还增加了自动探测（Windows）逻辑：若未设置变量，会尝试：

- `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`
- `C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe`

找到则自动启用，无需手动配置。

## 3. 验证安装

- 在 PowerShell 执行：
  ```powershell
  tesseract --version
  ```
  能看到版本信息即表示系统 PATH 可用（若不可用也没关系，项目内会通过 `TESSERACT_CMD` 直接使用）。

- 运行项目摄取脚本：
  ```powershell
  python ingest.py
  ```
  之前出现的 `OCR 回退失败: tesseract is not installed or it's not in your PATH` 应该消失。

## 4. 常见问题

- 报错 `Error opening data file .../tessdata/chi_sim.traineddata`：
  - 检查 `chi_sim.traineddata` 是否放在正确的 `tessdata` 目录。
  - 路径中不要包含中文或空格（尽量使用默认路径）。

- 仍然报 `tesseract not found`：
  - 在 `.env` 写入绝对路径的 `TESSERACT_CMD`。
  - 确认文件存在：`C:\\Program Files\\Tesseract-OCR\\tesseract.exe`。

- OCR 速度慢或识别不准：
  - 优先使用文本层解析（非扫描件无需 OCR）。
  - 仅对扫描页启用 OCR（项目会自动回退）。
  - 可以将 `OCR_LANG` 调整为与文档一致的语言组合（如仅中文 `chi_sim`）。

## 5. 相关配置回顾

- `.env.example` 已提供示例：
  ```env
  TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
  OCR_LANG=chi_sim+eng
  ```
- `ingest.py` 会读取 `TESSERACT_CMD` 或 `ingestion_config.yml` 中的 `tesseract_cmd`，两者都未设置时尝试自动探测。

