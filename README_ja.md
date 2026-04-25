# LLMTranslate (日本語)

[English Version (README.md)](README.md)

Vision機能を備えたLLM（OpenAI互換API）を使用して、Windowsデスクトップ画面を翻訳するツール。

<p align="center">
  <img src="src/resources/icon.png" width="128" height="128" alt="LLMTranslate アイコン">
</p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-blue.svg)](https://www.microsoft.com/windows)

## ✨ 主な機能

- **画面オーバーレイ**: 翻訳範囲を指定するリサイズ・移動可能な赤い枠を表示。
- **LLMによる翻訳**: キャプチャした画像をOpenAI互換API（LM Studio, OpenAI等）に送信して翻訳。
- **フローティング結果ウィンドウ**: 翻訳結果を枠のすぐ横に半透明ウィンドウで表示。
- **手動翻訳モード**: UIボタンまたはタスクトレイメニューから翻訳を実行。
- **自動監視モード**: 枠内の変化を自動検出し、テキストが変わった時のみ自動で翻訳。
- **多言語UI**: 10言語に対応（日本語、英語、フランス語、ドイツ語、タイ語、中国語、ポルトガル語、スペイン語、韓国語）。
- **タスクトレイ常駐**: 全ての操作にタスクバーのアイコンからアクセス可能。
- **詳細な推論設定**: Temperature, Max Tokens, Top Pなど、LM Studio準拠のパラメータを調整可能。
- **プリセット管理**: APIサーバーやモデルごとに設定を保存し、素早く切り替え。

## 🌍 対応UI言語

LLMTranslate のインターフェースは以下の言語に対応しています：
- 日本語
- 英語 (English)
- フランス語 (Français)
- ドイツ語 (Deutsch)
- タイ語 (ไทย)
- 中国語 簡体字 (中文 - 简体)
- 中国語 繁体字 (中文 - 繁體)
- ポルトガル語 - ブラジル (Português - Brasil)
- スペイン語 - ラテンアメリカ (Español - Latinoamérica)
- 韓国語 (한국어)

*アプリ起動時にOSの言語設定を自動的に検出します。*

## 📸 デモ

<p align="center">
  <img src="demo.gif" alt="LLMTranslate デモ">
</p>

## 🚀 クイックスタート

### 必要環境

- Windows 10/11
- Python 3.11 以上
- (推奨) [LM Studio](https://lmstudio.ai/) または OpenAI APIキー

### インストール

1. リポジトリをクローン:
   ```bash
   git clone https://github.com/yourusername/LLMTranslate.git
   cd LLMTranslate
   ```

2. 依存パッケージのインストール:
   ```bash
   pip install -r requirements.txt
   ```

### 起動

```bash
python run.py
```

## 📖 使い方

### 基本操作

1. アプリを起動するとタスクトレイにアイコンが表示されます。
2. 赤い枠線が表示されます。ドラッグで移動、四隅でリサイズします。
3. 翻訳したいテキストが枠内に入るように合わせます。
4. オーバーレイ枠上の**翻訳ボタン**をクリックするか、トレイアイコン右クリックから「翻訳を実行」を選択します。
5. 枠の横に翻訳結果が表示されます。

### 操作方法

- **翻訳ボタン (枠上)**: 手動翻訳を開始します。
- **自動監視切替**: 自動検出のON/OFFを切り替えます。
- **トレイメニュー**: 設定、プリセット、手動操作にアクセスできます。

### ショートカットキーについて

グローバルショートカット（`Ctrl+Shift+T` など）も設定されていますが、アクティブなウィンドウの状態によっては動作しない場合があります。確実な操作にはUI上のボタンを使用することを推奨します。

### 自動監視モード

有効にすると、一定間隔で枠内をスキャンし、大きな変化（テキストの更新など）を検出したときのみ自動的に翻訳リクエストを送信します。

## ⚙️ 設定

タスクトレイ右クリック -> 「設定...」から設定ダイアログを開きます。

### サーバー設定

- **API Base URL**: OpenAI互換エンドポイント（例: LM Studioは `http://localhost:1234/v1`）
- **API Key**: APIキー（LM Studioの場合は空でOK）
- **Model**: モデル名（例: `gpt-4o`, `lmstudio-community/...`）

### 推論パラメータ

LM Studioの設定項目に準拠。生成のランダム性や最大トークン数などを調整できます。

### プリセット

設定画面上部のバーから、現在の設定を保存・読み込み・削除できます。OpenAI用、ローカルLLM用などで使い分けると便利です。

## 🔗 LM Studio との連携

1. LM Studioを起動し、**Vision対応モデル**をロードします。
2. Local Serverを起動します（デフォルト: `http://localhost:1234`）。
3. LLMTranslateの設定を以下のように変更します:
   - **API Base URL**: `http://localhost:1234/v1`
   - **API Key**: (空欄)
   - **Model**: LM Studioに表示されているモデル識別子

## 📦 ビルド（単一EXEの生成）

```bash
pip install pyinstaller
python tools/generate_icon.py   # Windows用アイコン生成
pyinstaller build.spec
```

`dist/LLMTranslate.exe` が生成されます。

## 🛠️ 技術スタック

- **UI**: PySide6 (Qt for Python)
- **キャプチャ**: mss
- **画像処理**: Pillow（差分検出に ImageChops / ImageStat を使用）
- **通信**: httpx (Async)
- **ビルド**: PyInstaller

## 📄 ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。
