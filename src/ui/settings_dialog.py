"""設定画面 - 5タブ構成 + プリセット管理バー"""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.config import ConfigManager, DEFAULT_PRESET
from ..core.i18n import tr, SUPPORTED_LANGUAGES
from ..core.logger import set_log_level

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


# 翻訳先言語リスト
TARGET_LANGUAGES = [
    "Japanese",
    "English",
    "Chinese (Simplified)",
    "Chinese (Traditional)",
    "Korean",
    "French",
    "German",
    "Spanish",
    "Portuguese",
    "Italian",
    "Russian",
    "Arabic",
    "Thai",
    "Vietnamese",
    "Indonesian",
]


class ColorButton(QPushButton):
    """色選択ボタン"""

    color_changed = Signal(str)

    def __init__(self, color: str = "#FF0000", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._update_style()
        self.clicked.connect(self._pick_color)
        self.setFixedWidth(80)

    def _update_style(self) -> None:
        self.setText(self._color)
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; color: {'black' if self._is_light() else 'white'}; border: 1px solid #888; border-radius: 3px; }}"
        )

    def _is_light(self) -> bool:
        c = QColor(self._color)
        return (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 > 128

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, tr("settings.border_color"))
        if color.isValid():
            self._color = color.name()
            self._update_style()
            self.color_changed.emit(self._color)

    def get_color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._update_style()


class SettingsDialog(QDialog):
    """
    設定ダイアログ。
    プリセット管理バー + 5タブ（サーバー/推論/プロンプト/表示/監視）構成。

    Signals
    -------
    settings_applied: 設定が適用されたとき
    """

    settings_applied = Signal()

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._current_preset_data: dict[str, Any] = {}

        self.setWindowTitle(tr("settings.title"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)

        self._build_ui()
        self._load_preset(self._config.get_active_preset_name())

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # プリセット管理バー
        main_layout.addWidget(self._build_preset_bar())

        # タブウィジェット
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_server_tab(), tr("settings.tab.server"))
        self._tabs.addTab(self._build_inference_tab(), tr("settings.tab.inference"))
        self._tabs.addTab(self._build_prompt_tab(), tr("settings.tab.prompt"))
        self._tabs.addTab(self._build_display_tab(), tr("settings.tab.display"))
        self._tabs.addTab(self._build_monitor_tab(), tr("settings.tab.monitor"))
        main_layout.addWidget(self._tabs)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        main_layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # プリセット管理バー
    # ------------------------------------------------------------------

    def _build_preset_bar(self) -> QGroupBox:
        group = QGroupBox(tr("settings.preset"))
        layout = QHBoxLayout(group)
        layout.setContentsMargins(8, 4, 8, 4)

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(160)
        self._preset_combo.currentTextChanged.connect(self._on_preset_selected)
        layout.addWidget(self._preset_combo)

        save_btn = QPushButton(tr("settings.save"))
        save_btn.setToolTip(tr("settings.save"))
        save_btn.clicked.connect(self._on_preset_save)
        layout.addWidget(save_btn)

        save_as_btn = QPushButton(tr("settings.save_as"))
        save_as_btn.clicked.connect(self._on_preset_save_as)
        layout.addWidget(save_as_btn)

        delete_btn = QPushButton(tr("settings.delete"))
        delete_btn.setToolTip(tr("settings.delete"))
        delete_btn.clicked.connect(self._on_preset_delete)
        layout.addWidget(delete_btn)

        self._refresh_preset_combo()
        return group

    def _refresh_preset_combo(self) -> None:
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for name in self._config.get_preset_names():
            self._preset_combo.addItem(name)
        active = self._config.get_active_preset_name()
        idx = self._preset_combo.findText(active)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.blockSignals(False)

    def _on_preset_selected(self, name: str) -> None:
        if name:
            self._load_preset(name)

    def _on_preset_save(self) -> None:
        name = self._preset_combo.currentText()
        if not name:
            return
        data = self._collect_preset_data()
        self._config.save_preset(name, data)
        QMessageBox.information(self, tr("settings.save"), tr("msg.save_success", name=name))

    def _on_preset_save_as(self) -> None:
        name, ok = QInputDialog.getText(
            self, tr("settings.save_as"), tr("settings.save_as")
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self._config.get_preset_names():
            reply = QMessageBox.question(
                self,
                tr("settings.save_as"),
                tr("msg.overwrite_confirm", name=name),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        data = self._collect_preset_data()
        self._config.save_preset(name, data)
        self._refresh_preset_combo()
        idx = self._preset_combo.findText(name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        QMessageBox.information(self, tr("settings.save"), tr("msg.save_success", name=name))

    def _on_preset_delete(self) -> None:
        name = self._preset_combo.currentText()
        if name == "default":
            return
        reply = QMessageBox.question(
            self,
            tr("settings.delete"),
            tr("msg.delete_confirm", name=name),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._config.delete_preset(name)
        self._refresh_preset_combo()
        self._load_preset(self._config.get_active_preset_name())

    # ------------------------------------------------------------------
    # タブ1: サーバー設定
    # ------------------------------------------------------------------

    def _build_server_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._api_url = QLineEdit()
        self._api_url.setPlaceholderText("http://localhost:1234/v1")
        form.addRow(tr("settings.api_base"), self._api_url)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        form.addRow(tr("settings.api_key"), self._api_key)

        self._model = QLineEdit()
        self._model.setPlaceholderText("例: gpt-4o, local-model")
        form.addRow(tr("settings.model"), self._model)

        self._timeout = QSpinBox()
        self._timeout.setRange(5, 300)
        self._timeout.setSuffix(" s")
        form.addRow(tr("settings.timeout"), self._timeout)

        # ログレベル（グローバル設定）
        self._log_level = QComboBox()
        for lvl in LOG_LEVELS:
            self._log_level.addItem(lvl)
        current_level = self._config.get_log_level()
        idx = self._log_level.findText(current_level)
        if idx >= 0:
            self._log_level.setCurrentIndex(idx)
        form.addRow(tr("settings.log_level"), self._log_level)

        return widget

    # ------------------------------------------------------------------
    # タブ2: 推論パラメータ
    # ------------------------------------------------------------------

    def _build_inference_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._temperature = QDoubleSpinBox()
        self._temperature.setRange(0.0, 2.0)
        self._temperature.setSingleStep(0.05)
        self._temperature.setDecimals(2)
        form.addRow(tr("settings.temperature"), self._temperature)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(1, 32768)
        self._max_tokens.setSingleStep(256)
        form.addRow(tr("settings.max_tokens"), self._max_tokens)

        self._top_p = QDoubleSpinBox()
        self._top_p.setRange(0.0, 1.0)
        self._top_p.setSingleStep(0.05)
        self._top_p.setDecimals(2)
        form.addRow(tr("settings.top_p"), self._top_p)

        self._top_k = QSpinBox()
        self._top_k.setRange(0, 1000)
        form.addRow(tr("settings.top_k"), self._top_k)

        self._freq_penalty = QDoubleSpinBox()
        self._freq_penalty.setRange(-2.0, 2.0)
        self._freq_penalty.setSingleStep(0.1)
        self._freq_penalty.setDecimals(2)
        form.addRow(tr("settings.freq_penalty"), self._freq_penalty)

        self._pres_penalty = QDoubleSpinBox()
        self._pres_penalty.setRange(-2.0, 2.0)
        self._pres_penalty.setSingleStep(0.1)
        self._pres_penalty.setDecimals(2)
        form.addRow(tr("settings.pres_penalty"), self._pres_penalty)

        self._repeat_penalty = QDoubleSpinBox()
        self._repeat_penalty.setRange(0.0, 2.0)
        self._repeat_penalty.setSingleStep(0.05)
        self._repeat_penalty.setDecimals(2)
        form.addRow(tr("settings.repeat_penalty"), self._repeat_penalty)

        self._seed = QSpinBox()
        self._seed.setRange(-1, 2147483647)
        form.addRow(tr("settings.seed"), self._seed)

        self._stop_sequences = QLineEdit()
        form.addRow(tr("settings.stop_seq"), self._stop_sequences)

        scroll.setWidget(inner)
        return scroll

    # ------------------------------------------------------------------
    # タブ3: プロンプト設定
    # ------------------------------------------------------------------

    def _build_prompt_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 翻訳先言語
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel(tr("settings.target_lang")))
        self._target_language = QComboBox()
        for lang in TARGET_LANGUAGES:
            self._target_language.addItem(lang)
        lang_layout.addWidget(self._target_language)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)

        # システムプロンプト
        layout.addWidget(QLabel(tr("settings.system_prompt")))
        self._system_prompt = QTextEdit()
        self._system_prompt.setPlaceholderText(
            "{target_language} は翻訳先言語に自動置換されます"
        )
        self._system_prompt.setMinimumHeight(180)
        layout.addWidget(self._system_prompt)

        reset_btn = QPushButton(tr("settings.reset_prompt"))
        reset_btn.clicked.connect(self._reset_system_prompt)
        layout.addWidget(reset_btn)

        return widget

    def _reset_system_prompt(self) -> None:
        from ..core.config import DEFAULT_PRESET
        self._system_prompt.setPlainText(
            DEFAULT_PRESET["prompt"]["system_prompt"]
        )

    # ------------------------------------------------------------------
    # タブ4: 表示設定
    # ------------------------------------------------------------------

    def _build_display_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        # UI言語
        self._ui_language = QComboBox()
        self._ui_language.addItem("Auto", "auto")
        for code, name in SUPPORTED_LANGUAGES.items():
            self._ui_language.addItem(name, code)
        
        # 現在の言語を選択
        current_ui_lang = self._config.get_ui_language()
        idx = self._ui_language.findData(current_ui_lang)
        if idx >= 0:
            self._ui_language.setCurrentIndex(idx)
        
        form.addRow(tr("settings.ui_language"), self._ui_language)

        form.addRow(QWidget()) # Spacer

        # 枠線の色
        self._border_color_btn = ColorButton()
        form.addRow(tr("settings.border_color"), self._border_color_btn)

        # 枠線の太さ
        self._border_width = QSpinBox()
        self._border_width.setRange(1, 10)
        self._border_width.setSuffix(" px")
        form.addRow(tr("settings.border_width"), self._border_width)

        # 結果ウィンドウの不透明度
        opacity_layout = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(20, 100)
        self._opacity_slider.setTickInterval(10)
        self._opacity_label = QLabel("90%")
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        form.addRow(tr("settings.opacity"), opacity_layout)

        # フォントサイズ
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 32)
        self._font_size.setSuffix(" pt")
        form.addRow(tr("settings.font_size"), self._font_size)

        # 結果ウィンドウ幅
        self._result_width = QSpinBox()
        self._result_width.setRange(200, 800)
        self._result_width.setSuffix(" px")
        form.addRow(tr("settings.result_width"), self._result_width)

        return widget

    # ------------------------------------------------------------------
    # タブ5: 自動監視設定
    # ------------------------------------------------------------------

    def _build_monitor_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._monitor_interval = QDoubleSpinBox()
        self._monitor_interval.setRange(0.5, 60.0)
        self._monitor_interval.setSingleStep(0.5)
        self._monitor_interval.setDecimals(1)
        self._monitor_interval.setSuffix(" s")
        form.addRow(tr("settings.monitor_interval"), self._monitor_interval)

        threshold_layout = QHBoxLayout()
        self._change_threshold = QDoubleSpinBox()
        self._change_threshold.setRange(0.001, 1.0)
        self._change_threshold.setSingleStep(0.005)
        self._change_threshold.setDecimals(3)
        threshold_layout.addWidget(self._change_threshold)
        threshold_layout.addWidget(QLabel("(0.001 ~ 1.0)"))
        form.addRow(tr("settings.threshold"), threshold_layout)

        form.addRow(QWidget()) # Spacer

        self._use_ocr_precheck = QCheckBox(tr("settings.ocr_precheck"))
        form.addRow(self._use_ocr_precheck)

        self._tesseract_path = QLineEdit()
        self._tesseract_path.setPlaceholderText("C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
        form.addRow(tr("settings.tesseract_path"), self._tesseract_path)

        return widget

    # ------------------------------------------------------------------
    # データ読み込み・収集
    # ------------------------------------------------------------------

    def _load_preset(self, name: str) -> None:
        """指定プリセットの値をUIに反映"""
        presets = self._config._data.get("presets", {})
        from ..core.config import _deep_merge
        raw = presets.get(name, {})
        data = _deep_merge(DEFAULT_PRESET, raw)

        s = data["server"]
        self._api_url.setText(s.get("api_base_url", ""))
        self._api_key.setText(s.get("api_key", ""))
        self._model.setText(s.get("model", ""))
        self._timeout.setValue(s.get("timeout", 60))

        inf = data["inference"]
        self._temperature.setValue(inf.get("temperature", 0.3))
        self._max_tokens.setValue(inf.get("max_tokens", 2048))
        self._top_p.setValue(inf.get("top_p", 0.95))
        self._top_k.setValue(inf.get("top_k", 40))
        self._freq_penalty.setValue(inf.get("frequency_penalty", 0.0))
        self._pres_penalty.setValue(inf.get("presence_penalty", 0.0))
        self._repeat_penalty.setValue(inf.get("repeat_penalty", 1.1))
        self._seed.setValue(inf.get("seed", -1))
        self._stop_sequences.setText(inf.get("stop_sequences", ""))

        p = data["prompt"]
        lang = p.get("target_language", "Japanese")
        idx = self._target_language.findText(lang)
        self._target_language.setCurrentIndex(idx if idx >= 0 else 0)
        self._system_prompt.setPlainText(p.get("system_prompt", ""))

        d = data["display"]
        self._border_color_btn.set_color(d.get("border_color", "#FF0000"))
        self._border_width.setValue(d.get("border_width", 2))
        self._opacity_slider.setValue(int(d.get("result_opacity", 0.9) * 100))
        self._font_size.setValue(d.get("font_size", 14))
        self._result_width.setValue(d.get("result_width", 350))

        m = data["monitor"]
        self._monitor_interval.setValue(m.get("interval", 2.0))
        self._change_threshold.setValue(m.get("change_threshold", 0.05))
        self._use_ocr_precheck.setChecked(m.get("use_ocr_precheck", False))
        self._tesseract_path.setText(m.get("tesseract_path", ""))

        # ログレベル（グローバル設定 - プリセットに依存しない）
        log_level = self._config.get_log_level()
        idx_log = self._log_level.findText(log_level)
        if idx_log >= 0:
            self._log_level.setCurrentIndex(idx_log)

        # プリセットコンボを同期
        idx2 = self._preset_combo.findText(name)
        if idx2 >= 0:
            self._preset_combo.blockSignals(True)
            self._preset_combo.setCurrentIndex(idx2)
            self._preset_combo.blockSignals(False)

    def _collect_preset_data(self) -> dict[str, Any]:
        """UIの現在値からプリセットデータを構築"""
        return {
            "server": {
                "api_base_url": self._api_url.text().strip(),
                "api_key": self._api_key.text(),
                "model": self._model.text().strip(),
                "timeout": self._timeout.value(),
            },
            "inference": {
                "temperature": self._temperature.value(),
                "max_tokens": self._max_tokens.value(),
                "top_p": self._top_p.value(),
                "top_k": self._top_k.value(),
                "frequency_penalty": self._freq_penalty.value(),
                "presence_penalty": self._pres_penalty.value(),
                "repeat_penalty": self._repeat_penalty.value(),
                "seed": self._seed.value(),
                "stop_sequences": self._stop_sequences.text().strip(),
            },
            "prompt": {
                "system_prompt": self._system_prompt.toPlainText(),
                "target_language": self._target_language.currentText(),
            },
            "display": {
                "border_color": self._border_color_btn.get_color(),
                "border_width": self._border_width.value(),
                "result_opacity": self._opacity_slider.value() / 100.0,
                "font_size": self._font_size.value(),
                "result_width": self._result_width.value(),
            },
            "monitor": {
                "interval": self._monitor_interval.value(),
                "change_threshold": self._change_threshold.value(),
                "use_ocr_precheck": self._use_ocr_precheck.isChecked(),
                "tesseract_path": self._tesseract_path.text().strip(),
            },
        }

    # ------------------------------------------------------------------
    # ボタンハンドラ
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        # UI言語設定の変更チェック
        old_lang = self._config.get_ui_language()
        new_lang = self._ui_language.currentData()

        name = self._preset_combo.currentText()
        data = self._collect_preset_data()
        self._config.save_preset(name, data)
        self._config.set_active_preset(name)

        if old_lang != new_lang:
            self._config.set_ui_language(new_lang)
            QMessageBox.information(
                self,
                tr("settings.restart_required"),
                tr("settings.restart_msg")
            )

        # ログレベルの変更を即座に反映
        new_log_level = self._log_level.currentText()
        self._config.set_log_level(new_log_level)
        set_log_level(new_log_level)

        self.settings_applied.emit()

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()
