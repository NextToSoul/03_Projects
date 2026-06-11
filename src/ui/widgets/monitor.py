"""
PPCU TestBench — 报文收发监视器
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Slot
from PySide6.QtGui import QColor, QTextCharFormat, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPlainTextEdit, QTableView, QPushButton,
    QCheckBox, QLabel, QHeaderView,
)

from ...core.signals import EngineSignals


class FrameTableModel(QAbstractTableModel):
    """报文结构化表格模型"""

    def __init__(self):
        super().__init__()
        self._rows: list[list] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["时间","方向","标识符","APID","序列号","校验"][section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        if index.column() < len(self._rows[index.row()]):
            return self._rows[index.row()][index.column()]
        return None

    def add_frame(self, ts, dr, hex_str, checksum_ok=True):
        ident = hex_str[:4] if len(hex_str) >= 4 else "--"
        apid = hex_str[6:10] if len(hex_str) >= 10 else "--"
        cs = "OK" if checksum_ok else "FAIL"
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append([ts, dr, ident.upper(), apid.upper(), "--", cs])
        self.endInsertRows()
        if len(self._rows) > 10000:
            self.beginRemoveRows(QModelIndex(), 0, len(self._rows)-10001)
            self._rows = self._rows[-10000:]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()


class MessageMonitor(QWidget):
    """实时报文收发显示"""

    def __init__(self, signals: EngineSignals):
        super().__init__()
        self._signals = signals
        self._auto_scroll = True
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("报文监视"))
        ctrl.addStretch()
        self._auto_cb = QCheckBox("自动滚动")
        self._auto_cb.setChecked(True)
        self._auto_cb.toggled.connect(lambda v: setattr(self, "_auto_scroll", v))
        ctrl.addWidget(self._auto_cb)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(clear_btn)
        layout.addLayout(ctrl)

        splitter = QSplitter(Qt.Vertical)
        self._hex_view = QPlainTextEdit()
        self._hex_view.setReadOnly(True)
        self._hex_view.setMaximumBlockCount(5000)
        self._hex_view.setFont(QFont("Consolas", 9))
        splitter.addWidget(self._hex_view)

        self._frame_model = FrameTableModel()
        self._frame_table = QTableView()
        self._frame_table.setModel(self._frame_model)
        self._frame_table.setAlternatingRowColors(True)
        self._frame_table.verticalHeader().hide()
        self._frame_table.horizontalHeader().setStretchLastSection(True)
        self._frame_table.setFont(QFont("Consolas", 9))
        splitter.addWidget(self._frame_table)
        splitter.setSizes([300, 150])
        layout.addWidget(splitter, stretch=1)

    def connect_signals(self):
        s = self._signals
        s.raw_frame_sent.connect(self._on_frame_sent)
        s.raw_frame_received.connect(self._on_frame_received)

    @Slot(str, str)
    def _on_frame_sent(self, ts, hex_str):
        self._add_line(ts, "> TX", hex_str, QColor(0, 0, 180))
        self._frame_model.add_frame(ts, "TX", hex_str, True)

    @Slot(str, str, bool)
    def _on_frame_received(self, ts, hex_str, ok):
        color = QColor(0, 120, 0) if ok else QColor(180, 0, 0)
        tag = " [OK]" if ok else " [FAIL]"
        self._add_line(ts, "< RX", hex_str + tag, color)
        self._frame_model.add_frame(ts, "RX", hex_str, ok)

    def _add_line(self, ts, dr, text, color):
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        fmt.setFont(QFont("Consolas", 9))
        self._hex_view.setCurrentCharFormat(fmt)
        self._hex_view.appendPlainText(f"[{ts}] {dr}  {text}")
        if self._auto_scroll:
            self._hex_view.moveCursor(self._hex_view.textCursor().End)

    def clear(self):
        self._hex_view.clear()
        self._frame_model.clear()
