"""
PPCU TestBench — 遥测轮询控制栏
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFrame,
)

from ...core.definitions import PollMode
from ...core.signals import EngineSignals
from ...core.models import TelemetryPackageDef
from ...core.telemetry.registry import TelemetryRegistry

logger = logging.getLogger(__name__)


class PackageRow(QFrame):
    """遥测包单行控制"""

    mode_changed = Signal(str, str)  # (package_name, mode_str)

    def __init__(self, pkg_def: TelemetryPackageDef):
        super().__init__()
        self.pkg = pkg_def
        self.setFrameShape(QFrame.StyledPanel)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # 包名
        layout.addWidget(QLabel(self.pkg.name), stretch=1)

        # 状态指示灯
        self._status_label = QLabel("○ \u7a7a\u95f2")
        self._status_label.setFixedWidth(80)
        layout.addWidget(self._status_label)

        # 操作按钮
        self._once_btn = QPushButton("\u25b6\u4e00\u6b21")
        self._once_btn.setFixedWidth(70)
        self._once_btn.clicked.connect(lambda: self.mode_changed.emit(self.pkg.name, "single"))
        layout.addWidget(self._once_btn)

        self._poll_btn = QPushButton("\u25cf\u8f6e\u8be2")
        self._poll_btn.setFixedWidth(70)
        self._poll_btn.clicked.connect(lambda: self.mode_changed.emit(self.pkg.name, "active"))
        layout.addWidget(self._poll_btn)

        self._pause_btn = QPushButton("\u23f8\u6682\u505c")
        self._pause_btn.setFixedWidth(70)
        self._pause_btn.clicked.connect(lambda: self.mode_changed.emit(self.pkg.name, "paused"))
        layout.addWidget(self._pause_btn)

    def set_status(self, mode: str):
        """更新状态显示"""
        if mode == "active":
            self._status_label.setText("\u25cf \u8f6e\u8be2\u4e2d")
            self._status_label.setStyleSheet("color: green;")
        elif mode == "single":
            self._status_label.setText("\u25b6 \u67e5\u8be2\u4e2d")
            self._status_label.setStyleSheet("color: blue;")
        elif mode == "paused":
            self._status_label.setText("\u23f8 \u5df2\u6682\u505c")
            self._status_label.setStyleSheet("color: orange;")
        else:
            self._status_label.setText("○ \u7a7a\u95f2")
            self._status_label.setStyleSheet("color: gray;")


class PollingControlBar(QWidget):
    """轮询控制栏 — 全局 + 逐包控制"""

    def __init__(self, registry: TelemetryRegistry, signals: EngineSignals):
        super().__init__()
        self._registry = registry
        self._signals = signals
        self._rows: dict[str, PackageRow] = {}
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        # 全局控制行
        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("\u8f6e\u8be2\u63a7\u5236"))
        global_row.addStretch()

        self._start_all_btn = QPushButton("\u25b6 \u542f\u52a8\u5168\u90e8")
        self._start_all_btn.clicked.connect(lambda: self._emit_all("active"))
        global_row.addWidget(self._start_all_btn)

        self._pause_all_btn = QPushButton("\u23f8 \u6682\u505c\u5168\u90e8")
        self._pause_all_btn.clicked.connect(lambda: self._emit_all("paused"))
        global_row.addWidget(self._pause_all_btn)

        self._stop_all_btn = QPushButton("\u25a0 \u505c\u6b62\u5168\u90e8")
        self._stop_all_btn.clicked.connect(lambda: self._emit_all("disabled"))
        global_row.addWidget(self._stop_all_btn)

        layout.addLayout(global_row)

        # 逐包控制行
        for pkg in self._registry.list_packages():
            row = PackageRow(pkg)
            row.mode_changed.connect(self._on_mode_changed)
            self._rows[pkg.name] = row
            layout.addWidget(row)

    def connect_signals(self):
        self._signals.polling_mode_changed.connect(self._on_polling_mode_changed)

    @Slot(str, str)
    def _on_mode_changed(self, pkg_name: str, mode_str: str):
        """用户点击了某个包的按钮"""
        if self._signals and hasattr(self._signals, 'polling_mode_changed'):
            self._signals.polling_mode_changed.emit(pkg_name, mode_str)
        row = self._rows.get(pkg_name)
        if row:
            row.set_status(mode_str)

    @Slot(str, str)
    def _on_polling_mode_changed(self, pkg_name: str, mode_str: str):
        """外部(引擎/系统)更新了轮询状态"""
        row = self._rows.get(pkg_name)
        if row:
            row.set_status(mode_str)

    def _emit_all(self, mode_str: str):
        for pkg_name in self._rows:
            self._signals.polling_mode_changed.emit(pkg_name, mode_str)
            row = self._rows[pkg_name]
            row.set_status(mode_str)

    def set_polling_enabled(self, enable: bool):
        """启用/禁用所有控制按钮"""
        self._start_all_btn.setEnabled(enable)
        self._pause_all_btn.setEnabled(enable)
        self._stop_all_btn.setEnabled(enable)
        for row in self._rows.values():
            for btn in [row._once_btn, row._poll_btn, row._pause_btn]:
                btn.setEnabled(enable)
