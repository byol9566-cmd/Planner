from __future__ import annotations

import json
import threading
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTime

_DARK_STYLE = """
QDialog, QGroupBox, QLabel, QComboBox, QSpinBox, QTimeEdit, QPushButton {
    background-color: #0D0D0F;
    color: #E0E0EE;
}
QGroupBox {
    border: 1px solid #2A2A3A;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    color: #A0A0CC;
}
QComboBox, QSpinBox, QTimeEdit {
    background-color: #1A1A2E;
    border: 1px solid #2A2A3A;
    border-radius: 3px;
    padding: 2px 6px;
    color: #E0E0EE;
}
QComboBox::drop-down {
    border: none;
}
QPushButton {
    background-color: #1E1E3A;
    border: 1px solid #3A3A5A;
    border-radius: 4px;
    padding: 4px 12px;
    color: #E0E0EE;
}
QPushButton:hover {
    background-color: #2A2A4A;
}
QDialogButtonBox QPushButton {
    background-color: #1E1E3A;
    border: 1px solid #3A3A5A;
    border-radius: 4px;
    padding: 4px 12px;
    color: #E0E0EE;
}
"""

_VOICES = [
    "ko-KR-SunHiNeural",
    "ko-KR-InJoonNeural",
    "ko-KR-HyunsuNeural",
    "ko-KR-BongJinNeural",
    "ko-KR-GookMinNeural",
    "ko-KR-JiMinNeural",
    "ko-KR-SeoHyeonNeural",
]

_RATES = ["-50%", "-25%", "+0%", "+25%", "+50%"]


class SettingsDialog(QDialog):
    settings_changed = Signal()

    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self.setWindowTitle("설정")
        self.setMinimumWidth(380)
        self.setStyleSheet(_DARK_STYLE)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        # TTS 섹션
        tts_group = QGroupBox("TTS")
        tts_form = QFormLayout(tts_group)

        self._voice_combo = QComboBox()
        self._voice_combo.addItems(_VOICES)
        tts_form.addRow("음성", self._voice_combo)

        self._rate_combo = QComboBox()
        self._rate_combo.addItems(_RATES)
        tts_form.addRow("속도", self._rate_combo)

        preview_btn = QPushButton("🔊 미리듣기")
        preview_btn.clicked.connect(self._preview_tts)
        tts_form.addRow("", preview_btn)

        root_layout.addWidget(tts_group)

        # 알림 섹션
        notif_group = QGroupBox("알림")
        notif_form = QFormLayout(notif_group)

        self._pre_notify_spin = QSpinBox()
        self._pre_notify_spin.setRange(0, 30)
        self._pre_notify_spin.setSuffix(" 분")
        notif_form.addRow("사전 알림", self._pre_notify_spin)

        self._quiet_start_edit = QTimeEdit()
        self._quiet_start_edit.setDisplayFormat("HH:mm")
        notif_form.addRow("무음 시작", self._quiet_start_edit)

        self._quiet_end_edit = QTimeEdit()
        self._quiet_end_edit.setDisplayFormat("HH:mm")
        notif_form.addRow("무음 종료", self._quiet_end_edit)

        root_layout.addWidget(notif_group)

        # Notion 섹션
        notion_group = QGroupBox("Notion 동기화 (단방향)")
        notion_form = QFormLayout(notion_group)

        self._notion_token_edit = QLineEdit()
        self._notion_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._notion_token_edit.setPlaceholderText("secret_xxx... (Integration token)")
        notion_form.addRow("토큰", self._notion_token_edit)

        self._notion_db_edit = QLineEdit()
        self._notion_db_edit.setPlaceholderText("32자리 데이터베이스 ID")
        notion_form.addRow("DB ID", self._notion_db_edit)

        self._notion_enabled_chk = QCheckBox("자동 동기화 (편집/완료/메모 저장 시 push)")
        notion_form.addRow("", self._notion_enabled_chk)

        notion_help = QLabel(
            "1) notion.so/my-integrations 에서 Integration 생성 → token 복사\n"
            "2) DB 만들기 (열: Title, Date, Time, Kind, Note, BlockKey, Done)\n"
            "3) DB 페이지 우상단 '⋯ → 연결 추가'로 integration 연결\n"
            "4) DB URL의 32자리 ID를 위에 붙여넣기"
        )
        notion_help.setStyleSheet("color:#888899; font-size:10px;")
        notion_help.setWordWrap(True)
        notion_form.addRow("", notion_help)

        root_layout.addWidget(notion_group)

        # 확인 / 취소
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # 값 로드 / 저장
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        try:
            with open(self._config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_values(self) -> None:
        cfg = self._load_config()
        s = cfg.get("settings", {})

        voice = s.get("tts_voice", _VOICES[0])
        idx = self._voice_combo.findText(voice)
        if idx >= 0:
            self._voice_combo.setCurrentIndex(idx)

        rate = s.get("tts_rate", "+0%")
        r_idx = self._rate_combo.findText(rate)
        if r_idx >= 0:
            self._rate_combo.setCurrentIndex(r_idx)

        self._pre_notify_spin.setValue(s.get("pre_notify_minutes", 5))

        qs = s.get("quiet_start", "22:00")
        qe = s.get("quiet_end", "08:00")
        self._quiet_start_edit.setTime(QTime.fromString(qs, "HH:mm"))
        self._quiet_end_edit.setTime(QTime.fromString(qe, "HH:mm"))

        notion = s.get("notion", {}) or {}
        self._notion_token_edit.setText(notion.get("token", ""))
        self._notion_db_edit.setText(notion.get("database_id", ""))
        self._notion_enabled_chk.setChecked(bool(notion.get("enabled", False)))

    def _save_and_accept(self) -> None:
        try:
            with open(self._config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        if "settings" not in cfg:
            cfg["settings"] = {}

        cfg["settings"]["tts_voice"] = self._voice_combo.currentText()
        cfg["settings"]["tts_rate"] = self._rate_combo.currentText()
        cfg["settings"]["pre_notify_minutes"] = self._pre_notify_spin.value()
        cfg["settings"]["quiet_start"] = self._quiet_start_edit.time().toString("HH:mm")
        cfg["settings"]["quiet_end"] = self._quiet_end_edit.time().toString("HH:mm")
        cfg["settings"]["notion"] = {
            "token": self._notion_token_edit.text().strip(),
            "database_id": self._notion_db_edit.text().strip(),
            "enabled": self._notion_enabled_chk.isChecked(),
        }

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        self.settings_changed.emit()
        self.accept()

    # ------------------------------------------------------------------
    # TTS 미리듣기
    # ------------------------------------------------------------------

    def _preview_tts(self) -> None:
        voice = self._voice_combo.currentText()
        rate = self._rate_combo.currentText()

        def _run() -> None:
            try:
                from core.tts import TTS
                TTS(voice, rate).speak("안녕하세요. 일정 알림 테스트입니다.")
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
