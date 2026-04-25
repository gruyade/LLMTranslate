# LLMTranslate

[日本語版 (README_ja.md)](README_ja.md)

Windows desktop screen translator using LLM (OpenAI-compatible APIs) with Vision capabilities.

<p align="center">
  <img src="src/resources/icon.png" width="128" height="128" alt="LLMTranslate Icon">
</p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-blue.svg)](https://www.microsoft.com/windows)

## ✨ Features

- **Overlay Capture**: Display a resizable/movable overlay frame to capture screen areas. (Frame color is customizable in settings.)
- **LLM-Powered Translation**: Send captured images to OpenAI-compatible APIs (LM Studio, OpenAI, etc.).
- **Floating Result Window**: Translation results appear in a semi-transparent window next to the frame.
- **Manual Mode**: Execute translation via the UI button or system tray menu.
- **Auto-Monitor Mode**: Automatically detect text changes in the frame and translate.
- **Multi-language UI**: Supports 10 languages (English, Japanese, French, German, Thai, Chinese, Portuguese, Spanish, Korean).
- **System Tray Integration**: Full control via the taskbar icon.
- **Fine-tuned Inference**: Adjust parameters like Temperature, Max Tokens, and Top P (compatible with LM Studio).
- **Presets**: Save and switch between different API/model configurations.

## 🎯 Use Cases

### Author's Intended Use
- Translating in-game text for games with no localization or poor-quality translations
- Reducing the effort of translating text that cannot be copied and pasted

### AI-Recommended Use Cases
- Navigating untranslated foreign software UIs
- Monitoring and translating live stream chat in a foreign language (Auto-Monitor Mode automatically translates new messages)
- Translating foreign-language text on remote desktops or virtual machines
- Translating copy-protected PDFs or DRM-locked e-books
- Real-time translation of foreign-language screens shared in video meetings (auto-translates as slides change)
- Translating Canvas/WebGL-based web apps and other screens where browser built-in translation doesn't work
- Checking reference translations while studying a foreign language

## 🌍 Supported UI Languages

LLMTranslate's interface is available in:
- English
- Japanese (日本語)
- French (Français)
- German (Deutsch)
- Thai (ไทย)
- Chinese Simplified (中文 - 简体)
- Chinese Traditional (中文 - 繁體)
- Portuguese - Brazil (Português - Brasil)
- Spanish - Latin America (Español - Latinoamérica)
- Korean (한국어)

*The app automatically detects your OS language on first launch.*

## 📸 Demo

<p align="center">
  <img src="demo.gif" alt="LLMTranslate Demo">
</p>

## 🚀 Quick Start

### Requirements

- Windows 10/11
- Python 3.11 or higher
- (Recommended) [LM Studio](https://lmstudio.ai/) or an OpenAI API Key

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/LLMTranslate.git
   cd LLMTranslate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Launch

```bash
python run.py
```

## 📖 Usage

### Basic Operation

1. Launch the app to see the icon in the system tray.
2. An overlay frame appears. Drag to move, resize via corners. (Frame color is customizable in settings.)
3. Align the frame with the text area you want to translate.
4. Click the **Translation Button** on the overlay frame (or right-click tray icon -> "Execute Translation").
5. The result appears in a floating window next to the frame.

### Controls

- **Translation Button (on Frame)**: Triggers manual translation.
- **Auto-Monitor Toggle**: Enables/disables automatic detection.
- **Tray Menu**: Access settings, presets, and manual controls.

### Hotkeys (Note)

*Global hotkeys are supported (`Ctrl+Shift+T` for translation, etc.), but their reliability may depend on the active window focus. Using the UI buttons is recommended for consistent operation.*

### Auto-Monitor Mode

When enabled, the app monitors the frame at set intervals and triggers translation only when significant changes (text updates) are detected.

## ⚙️ Configuration

Right-click the tray icon -> "Settings..." to open the configuration dialog.

### Server Settings

- **API Base URL**: OpenAI-compatible endpoint (e.g., LM Studio: `http://localhost:1234/v1`)
- **API Key**: Your API key (not required for LM Studio)
- **Model**: Model ID (e.g., `gpt-4o`, `lmstudio-community/...`)

### Inference Parameters (LM Studio compatible)

Adjust Temperature, Top P, Top K, Frequency Penalty, etc., to fine-tune the LLM output.

### Presets

Manage multiple configurations using the preset bar at the top of the settings dialog. Save different settings for OpenAI, LM Studio, or specific models.

## 🔗 LM Studio Integration

1. Start LM Studio and load a **Vision-enabled** model.
2. Start the Local Server (default: `http://localhost:1234`).
3. In LLMTranslate settings:
   - **API Base URL**: `http://localhost:1234/v1`
   - **API Key**: (leave empty)
   - **Model**: Use the identifier shown in LM Studio.

## 📦 Build (Standalone EXE)

```bash
pip install pyinstaller
python tools/generate_icon.py   # Generate Windows icons
pyinstaller build.spec
```

The executable will be generated in `dist/LLMTranslate.exe`.

## ⚠️ Disclaimer

This project was developed with the assistance of AI tools for personal hobby use.

- Normal use cases are expected to work correctly, but **edge cases are not fully covered**.
- **No warranty** is provided for any damages or losses resulting from the use of this software.
- Use at your own risk.
- This app captures the screen area within the overlay frame and sends the image **directly to the configured API**. If the content of the captured image is deemed inappropriate by the API provider, your account may be suspended or banned. **No responsibility is taken for any such consequences.**

## 🖥️ Development Environment

| Item | Details |
|------|---------|
| OS | Windows 11 |
| Language | Python 3.11 |
| IDE | Visual Studio Code |
| AI Assistance | Roo Code |
| Primary Model Used | Claude Opus 4.6 (Design), Sonnet 4.6 (Design, Implementation, Debugging), Google Gemini 3 Flash (Implementation) |
## 🛠️ Tech Stack

- **UI**: PySide6 (Qt for Python)
- **Capture**: mss
- **Image Processing**: Pillow (ImageChops / ImageStat for change detection)
- **Communication**: httpx (Async)
- **Build**: PyInstaller

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
