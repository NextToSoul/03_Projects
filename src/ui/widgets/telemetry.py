"""
PPCU TestBench — 遥测数据表面板
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, Signal, Slot,
)
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QHeaderView,
    QLabel, QComboBox, QHBoxLayout,
)

from ...core.signals import EngineSignals
from ...core.models import TelemetrySnapshot, TelemetryUpdate
from ...core.telemetry.registry import TelemetryRegistry

logger = logging.getLogger(__name__)


class TelemetryTableModel(QAbstractTableModel):
    """遥测数据模型 — 按包分组展平"""

    COLUMNS = ["参数ID", "参数名称", "原始值(hex)", "物理值", "单位"]

    def __init__(self, registry: TelemetryRegistry):
        super().__init__()
        self._registry = registry
        # 扁平化参数列表: [(package_name, TelemetryParam), ...]
        self._params: list[tuple[str, Any]] = []
        # 最新快照: param_id -> TelemetrySnapshot
        self._snapshots: dict[str, TelemetrySnapshot] = {}
        self._rebuild_params()

    def _rebuild_params(self):
        self.beginResetModel()
        self._params.clear()
        for pkg in self._registry.list_packages():
            for param in pkg.parameters:
                self._params.append((pkg.name, param))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._params)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        pkg_name, param = self._params[index.row()]
        snap = self._snapshots.get(param.id)

        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            col = index.column()
            if col == 0:
                return param.id
            elif col == 1:
                return param.name
            elif col == 2:
                if snap and snap.raw_bytes:
                    return snap.raw_bytes.hex(" ").upper()
                return "-"
            elif col == 3:
                if snap and snap.physical_value is not None:
                    v = snap.physical_value
                    if isinstance(v, float):
                        dec = param.decimal_places or 2
                        return f"{v:.{dec}f}"
                    return str(v)
                return "-"
            elif col == 4:
                return param.unit or "-"

        if role == Qt.ForegroundRole and snap:
            if isinstance(snap.physical_value, str) and "Unknown" in snap.physical_value:
                return QBrush(QColor(200, 80, 0))

        if role == Qt.ToolTipRole:
            pkg_info = f"包: {pkg_name} | 类型: {param.data_type}"
            if param.enum_values:
                vals = "; ".join(f"{k}={v}" for k, v in param.enum_values.items())
                pkg_info += f"\n枚举值: {vals}"
            return pkg_info

        return None

    def update_snapshot(self, package: str, snapshots: list[TelemetrySnapshot]):
        """更新遥测快照（从 signal 回调）"""
        for snap in snapshots:
            self._snapshots[snap.param_id] = snap
        # 只刷新有更新的行
        for snap in snapshots:
            for row, (pkg, param) in enumerate(self._params):
                if param.id == snap.param_id:
                    idx_start = self.index(row, 0)
                    idx_end = self.index(row, self.columnCount() - 1)
                    self.dataChanged.emit(idx_start, idx_end, [Qt.DisplayRole])
                    break

    def get_param_at(self, row: int) -> Any | None:
        if 0 <= row < len(self._params):
            return self._params[row][1]
        return None


class TelemetryTableView(QWidget):
    """遥测数据表视图组件"""

    def __init__(self, registry: TelemetryRegistry, signals: EngineSignals):
        super().__init__()
        self._registry = registry
        self._signals = signals
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 顶部工具栏: 包筛选
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("筛选:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("全部包")
        for pkg in self._registry.list_packages():
            self._filter_combo.addItem(pkg.name)
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)
        toolbar.addStretch()
        toolbar.addWidget(QLabel(f"参数数: {self._registry.total_params}"))
        layout.addLayout(toolbar)

        # 模型 + 视图
        self._model = TelemetryTableModel(self._registry)
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setColumnWidth(0, 80)
        self._table.setColumnWidth(1, 180)
        self._table.setColumnWidth(2, 120)
        self._table.setColumnWidth(3, 100)
        self._table.setColumnWidth(4, 60)
        font = QFont("Consolas", 9)
        self._table.setFont(font)
        layout.addWidget(self._table, stretch=1)

    def connect_signals(self):
        self._signals.telemetry_updated.connect(self._on_telemetry_updated)

    @Slot(str, list)
    def _on_telemetry_updated(self, package: str, snapshots: list):
        self._model.update_snapshot(package, snapshots)

    def _on_filter_changed(self, text: str):
        """按包筛选"""
        # 简单实现: 显示或隐藏行
        for row in range(self._model.rowCount()):
            pkg_name, _ = self._model._params[row]
            visible = text == "全部包" or pkg_name == text
            self._table.setRowHidden(row, not visible)

    def get_snapshot(self, param_id: str) -> TelemetrySnapshot | None:
        return self._model._snapshots.get(param_id)
