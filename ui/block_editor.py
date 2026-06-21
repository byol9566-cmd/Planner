from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core.config_loader import Block, save_override

KIND_OPTIONS = [
    "wake", "workout", "meal", "buffer", "deepwork",
    "reading", "theme", "marketing", "wrap", "winddown",
    "sleep", "light", "event",
]


class BlockRow(QWidget):
    sig_insert_after = Signal(object)   # emits self
    sig_delete = Signal(object)         # emits self

    def __init__(self, block: Block, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        # 시작 시간
        self.start_edit = QLineEdit(block.time)
        self.start_edit.setFixedWidth(50)
        self.start_edit.setPlaceholderText("HH:MM")
        layout.addWidget(self.start_edit)

        layout.addWidget(QLabel("~"))

        # 종료 시간
        self.end_edit = QLineEdit(block.end_time)
        self.end_edit.setFixedWidth(50)
        self.end_edit.setPlaceholderText("HH:MM")
        layout.addWidget(self.end_edit)

        # 제목
        self.title_edit = QLineEdit(block.title)
        self.title_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.title_edit)

        # 종류
        self.kind_box = QComboBox()
        self.kind_box.addItems(KIND_OPTIONS)
        idx = KIND_OPTIONS.index(block.kind) if block.kind in KIND_OPTIONS else 0
        self.kind_box.setCurrentIndex(idx)
        self.kind_box.setFixedWidth(88)
        layout.addWidget(self.kind_box)

        # 아래에 삽입
        ins_btn = QPushButton("＋")
        ins_btn.setFixedWidth(26)
        ins_btn.setToolTip("아래에 블록 삽입")
        ins_btn.clicked.connect(lambda: self.sig_insert_after.emit(self))
        layout.addWidget(ins_btn)

        # 삭제
        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(26)
        del_btn.clicked.connect(lambda: self.sig_delete.emit(self))
        layout.addWidget(del_btn)

    def to_block(self) -> Block | None:
        t = self.start_edit.text().strip()
        title = self.title_edit.text().strip()
        kind = self.kind_box.currentText()
        end = self.end_edit.text().strip()
        if not t or not title:
            return None
        return Block(t, title, kind, end)


class BlockEditorDialog(QDialog):
    def __init__(self, blocks: list[Block], title: str, on_save, parent=None):
        """
        on_save: callable(blocks: list[Block]) called when user saves
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        self.resize(620, 520)
        self._on_save_cb = on_save

        root = QVBoxLayout(self)

        # 컬럼 헤더
        hdr = QHBoxLayout()
        for text, width in [("시작", 50), ("", 12), ("종료", 50), ("제목", 0), ("종류", 88), ("", 26), ("", 26)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#888; font-size:10px;")
            if width:
                lbl.setFixedWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            hdr.addWidget(lbl)
        hdr.setSpacing(4)
        hdr.setContentsMargins(0, 0, 0, 0)
        root.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_widget)
        root.addWidget(scroll)

        for b in blocks:
            self._insert_row(b)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _make_row(self, block: Block) -> BlockRow:
        row = BlockRow(block, self._rows_widget)
        row.sig_insert_after.connect(self._on_insert_after)
        row.sig_delete.connect(self._on_delete)
        return row

    def _insert_row(self, block: Block, after: BlockRow | None = None) -> None:
        row = self._make_row(block)
        if after is None:
            # 맨 끝 (stretch 앞)
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        else:
            idx = self._rows_layout.indexOf(after)
            self._rows_layout.insertWidget(idx + 1, row)

    def _on_insert_after(self, sender: BlockRow) -> None:
        self._insert_row(Block("", "", "buffer"), after=sender)

    def _on_delete(self, sender: BlockRow) -> None:
        self._rows_layout.removeWidget(sender)
        sender.setParent(None)
        sender.deleteLater()

    def _save(self) -> None:
        blocks = []
        for i in range(self._rows_layout.count()):
            w = self._rows_layout.itemAt(i).widget()
            if isinstance(w, BlockRow):
                b = w.to_block()
                if b:
                    blocks.append(b)

        blocks.sort(key=lambda b: b.time if b.time != "24:00" else "99:99")
        self._on_save_cb(blocks)
        self.accept()


class TemplateEditorDialog(QDialog):
    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("기본 템플릿 편집")
        self.setMinimumWidth(680)
        self.resize(700, 600)
        self._config_path = config_path

        from core.config_loader import template_names, save_template
        import json
        self._save_template = save_template
        self._config_path = config_path

        root = QVBoxLayout(self)

        # 템플릿 선택
        top = QHBoxLayout()
        top.addWidget(QLabel("템플릿:"))
        self._type_box = QComboBox()
        names = template_names(config_path)
        for code, name in names.items():
            self._type_box.addItem(f"[{code}] {name}", userData=code)
        top.addWidget(self._type_box)
        top.addStretch()
        root.addLayout(top)

        # 블록 편집 영역 (재사용)
        self._editor_container = QVBoxLayout()
        root.addLayout(self._editor_container)
        self._editor: BlockEditorDialog | None = None

        self._type_box.currentIndexChanged.connect(self._load_template)
        self._load_template()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_template(self) -> None:
        import json
        code = self._type_box.currentData()
        with open(self._config_path, encoding="utf-8") as f:
            raw = json.load(f)
        raw_blocks = raw["templates"].get(code, {}).get("blocks", [])
        from core.config_loader import Block
        blocks = [Block(b["time"], b["title"], b["kind"], b.get("end_time", "")) for b in raw_blocks]

        # 기존 편집기 제거
        while self._editor_container.count():
            item = self._editor_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        inner = _InlineBlockEditor(blocks, lambda blks: self._on_save(code, blks), self)
        self._editor_container.addWidget(inner)

    def _on_save(self, code: str, blocks) -> None:
        self._save_template(code, blocks, self._config_path)
        try:
            from core.notion_sync import autosync_in_background
            overrides_dir = self._config_path.parent / "overrides"
            autosync_in_background(self._config_path, overrides_dir)
        except Exception:
            pass


class _InlineBlockEditor(QWidget):
    """BlockEditorDialog의 편집 영역만 위젯으로 분리."""

    def __init__(self, blocks, on_save, parent=None):
        super().__init__(parent)
        self._on_save_cb = on_save
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        for text, width in [("시작", 50), ("", 12), ("종료", 50), ("제목", 0), ("종류", 88), ("", 26), ("", 26)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#888; font-size:10px;")
            if width:
                lbl.setFixedWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            hdr.addWidget(lbl)
        hdr.setSpacing(4)
        hdr.setContentsMargins(0, 0, 0, 0)
        root.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_widget)
        root.addWidget(scroll)

        for b in blocks:
            self._insert_row(b)

        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

    def _make_row(self, block) -> BlockRow:
        row = BlockRow(block, self._rows_widget)
        row.sig_insert_after.connect(lambda r: self._insert_row(Block("", "", "buffer"), after=r))
        row.sig_delete.connect(lambda r: (self._rows_layout.removeWidget(r), r.setParent(None), r.deleteLater()))
        return row

    def _insert_row(self, block, after=None) -> None:
        row = self._make_row(block)
        if after is None:
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        else:
            idx = self._rows_layout.indexOf(after)
            self._rows_layout.insertWidget(idx + 1, row)

    def _save(self) -> None:
        from core.config_loader import Block
        blocks = []
        for i in range(self._rows_layout.count()):
            w = self._rows_layout.itemAt(i).widget()
            if isinstance(w, BlockRow):
                b = w.to_block()
                if b:
                    blocks.append(b)
        blocks.sort(key=lambda b: b.time if b.time != "24:00" else "99:99")
        self._on_save_cb(blocks)
