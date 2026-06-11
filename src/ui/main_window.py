from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
import threading
import asyncio
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QToolBar, QStatusBar,
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox,
    QMessageBox, QFileDialog, QApplication, QTableView,
    QTabWidget, QSplitter, QFrame, QHeaderView,
)
from ..core.signals import EngineSignals
from ..core.models import ProjectContext
from ..core.telemetry.registry import TelemetryRegistry, CommandRegistry
from .widgets.telemetry import TelemetryTableView
from .widgets.monitor import MessageMonitor
from .widgets.polling_control import PollingControlBar
logger = logging.getLogger(__name__)



class MainWindow(QMainWindow):
    """PPCU TestBench 主窗口"""

    def __init__(self, ctx: ProjectContext, signals: EngineSignals):
        super().__init__()
        self._ctx = ctx
        self._signals = signals
        self.setWindowTitle(f"PPCU 通用测试平台 — [{ctx.name}]")
        self.resize(1280, 800)
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """搭建主窗口布局"""
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_central_area()
        self._create_status_bar()

    # ───── 菜单栏 ─────
    def _create_menu_bar(self):
        mb = self.menuBar()

        fm = mb.addMenu("文件(&F)")
        fm.addAction("打开项目...")
        fm.addSeparator()
        fm.addAction("退出(&Q)", self.close, "Ctrl+Q")

        tm = mb.addMenu("测试(&T)")
        tm.addAction("运行全部用例")
        tm.addAction("停止测试")
        tm.addSeparator()
        tm.addAction("生成报告...")

        cm = mb.addMenu("配置(&C)")
        cm.addAction("遥测包管理...")
        cm.addAction("安全设置...")

        hm = mb.addMenu("帮助(&H)")
        hm.addAction("关于...")

    # ───── 工具栏 ─────
    def _create_tool_bar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)

        # 连接控制
        self._conn_btn = QPushButton("● 断开")
        self._conn_btn.setFixedWidth(120)
        self._conn_btn.clicked.connect(self._toggle_connection)
        tb.addWidget(self._conn_btn)

        tb.addSeparator()

        # 项目切换
        tb.addWidget(QLabel("项目:"))
        self._project_combo = QComboBox()
        self._project_combo.setFixedWidth(200)
        self._project_combo.addItem(self._ctx.name)
        tb.addWidget(self._project_combo)

        tb.addSeparator()

        # 轮询控制 - 全局
        self._poll_start_btn = QPushButton("▶ 启动轮询")
        self._poll_start_btn.clicked.connect(self._on_poll_start_all)
        tb.addWidget(self._poll_start_btn)

        self._poll_pause_btn = QPushButton("⏸ 暂停")
        self._poll_pause_btn.clicked.connect(self._on_poll_pause_all)
        tb.addWidget(self._poll_pause_btn)

        self._poll_stop_btn = QPushButton("■ 停止")
        self._poll_stop_btn.clicked.connect(self._on_poll_stop_all)
        tb.addWidget(self._poll_stop_btn)

    # ───── 中央区域 ─────
    def _create_central_area(self):
        """遥测表为主 + 右侧报文监视器"""
        splitter = QSplitter(Qt.Horizontal)

        # 左侧: 轮询控制 + 遥测表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._polling_bar = PollingControlBar(
            self._ctx.telemetry_registry, self._signals)
        left_layout.addWidget(self._polling_bar)

        self._telemetry_tabs = QTabWidget()
        tm_widget = TelemetryTableView(self._ctx.telemetry_registry, self._signals)
        self._telemetry_tabs.addTab(tm_widget, "遥测数据表")
        left_layout.addWidget(self._telemetry_tabs, stretch=1)

        splitter.addWidget(left_widget)

        # 右侧: 报文监视器
        self._monitor = MessageMonitor(self._signals)
        splitter.addWidget(self._monitor)

        splitter.setSizes([700, 400])
        self.setCentralWidget(splitter)

    # ───── 状态栏 ─────
    def _create_status_bar(self):
        sb = self.statusBar()
        self._status_label = QLabel("就绪")
        sb.addWidget(self._status_label, 1)
        self._pkg_status = QLabel("遥测包: 0/0 活跃")
        sb.addPermanentWidget(self._pkg_status)
        self._rx_status = QLabel("最近接收: --")
        sb.addPermanentWidget(self._rx_status)

    # ───── 信号连接 ─────
    def connect_signals(self):
        s = self._signals
        s.connection_changed.connect(self._on_connection_changed)
        s.telemetry_updated.connect(self._on_telemetry_updated)
        s.safety_alert.connect(self._on_safety_alert)
        s.error_occurred.connect(self._on_error)
        s.progress_update.connect(self._on_progress)

    # ───── 槽函数 ─────
    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, detail: str):
        if connected:
            self._conn_btn.setText("断开")
            self._conn_btn.setStyleSheet("color: red;")
            self._status_label.setText(f"已连接: {detail}")
        else:
            self._conn_btn.setText("连接")
            self._conn_btn.setStyleSheet("color: green;")
            self._status_label.setText(f"断开: {detail}")

    @Slot(str, list)
    def _on_telemetry_updated(self, package: str, snapshots: list):
        self._rx_status.setText(f"最近接收: {package}")

    @Slot(str, str)
    def _on_safety_alert(self, level: str, msg: str):
        self._status_label.setText(f"[{level}] {msg}")

    @Slot(str, str)
    def _on_error(self, source: str, msg: str):
        self._status_label.setText(f"错误 [{source}]: {msg}")

    @Slot(str, float)
    def _on_progress(self, msg: str, pct: float):
        self._status_label.setText(f"{msg} ({pct:.0f}%)")

    async def _do_connect(self):
        if self._ctx.transport:
            cfg = self._ctx.profile.transport_config if self._ctx.profile else {}
            ok = await self._ctx.transport.connect(cfg)
            if ok:
                self._signals.connection_changed.emit(True, f"{cfg.get('host')}:{cfg.get('port')}")
            else:
                self._signals.connection_changed.emit(False, "连接失败")

    async def _do_disconnect(self):
        if self._ctx.transport:
            await self._ctx.transport.disconnect()
            self._signals.connection_changed.emit(False, "已断开")

    def _toggle_connection(self):
        if not self._ctx.transport:
            return
        thread = threading.Thread(target=self._run_async_task, daemon=True)
        thread.start()
    
    def _run_async_task(self):
        if self._ctx.transport and self._ctx.transport.is_connected():
            asyncio.run(self._do_disconnect())
        else:
            asyncio.run(self._do_connect())

    def _on_poll_start_all(self):
        """启动全部遥测轮询"""
        from ..core.definitions import PollMode
        if hasattr(self._ctx, 'polling_manager') and self._ctx.polling_manager:
            self._ctx.polling_manager.start_all_default()

    def _on_poll_pause_all(self):
        from ..core.definitions import PollMode
        if hasattr(self._ctx, 'polling_manager') and self._ctx.polling_manager:
            self._ctx.polling_manager.pause_all()

    def _on_poll_stop_all(self):
        if hasattr(self._ctx, 'polling_manager') and self._ctx.polling_manager:
            self._ctx.polling_manager.stop_all()

    def update_package_status(self, active: int, total: int):
        self._pkg_status.setText(f"遥测包: {active}/{total} 活跃")

    @property
    def telemetry_table(self) -> TelemetryTableView | None:
        tw = self._telemetry_tabs.widget(0)
        return tw if isinstance(tw, TelemetryTableView) else None

    @property
    def monitor(self) -> MessageMonitor:
        return self._monitor

    @property
    def polling_bar(self) -> PollingControlBar:
        return self._polling_bar
