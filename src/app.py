"""
PPCU TestBench — 应用程序入口
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .config.loader import ProfileLoader
from .core.engine.project_switch import ProjectSwitcher
from .core.hardware.sequencer import SequenceManager
from .core.signals import EngineSignals
from .core.telemetry.cache import TelemetryCache
from .core.telemetry.poller import PollingManager
from .core.safety.guard import SafetyGuard
from .ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class TuiApp:
    """PPCU TestBench 应用 — 组装引擎 + UI"""

    def __init__(self, profile_path: str | Path = ""):
        self._profile_path = Path(profile_path) if profile_path else None
        self.signals = EngineSignals()
        self.telemetry_cache = TelemetryCache()
        self.seq_mgr = SequenceManager()
        self.polling_mgr = None
        self.safety = SafetyGuard()
        self.switcher = ProjectSwitcher()
        self.window: MainWindow | None = None

    async def initialize(self):
        """加载项目配置，创建窗口"""
        if self._profile_path and self._profile_path.exists():
            loader = ProfileLoader()
            ctx = await loader.load(self._profile_path)

            # 创建轮询管理器
            pm = PollingManager(
                ctx.transport, ctx.protocol,
                self.seq_mgr, self.telemetry_cache,
            )
            pm.set_registries(ctx.telemetry_registry, ctx.command_registry)
            for pkg in ctx.telemetry_registry.list_packages():
                pm.register_package(pkg)
            self.polling_mgr = pm
            ctx.polling_manager = pm

            # 安全
            if ctx.safety:
                self.safety = SafetyGuard(ctx.safety)

            # 创建主窗口
            self.window = MainWindow(ctx, self.signals)

            # 连接轮询状态变更信号
            pm.on_status_changed(
                lambda pkg, mode: self.signals.polling_mode_changed.emit(pkg, mode)
            )

            logger.info(f"Application initialized: {ctx.name}")
        else:
            logger.warning(f"No profile path provided or not found: {self._profile_path}")

    def show(self):
        if self.window:
            self.window.show()

    def start_polling_timer(self):
        """启动异步轮询计时器 (Qt Timer 驱动 asyncio)"""
        timer = QTimer()
        timer.timeout.connect(self._tick)
        timer.start(100)  # 100ms 检查一次

    def _tick(self):
        """每个 tick 执行一次 asyncio 事件循环"""
        loop = asyncio.get_event_loop()
        loop.call_soon(lambda: None)  # 触发一次事件循环处理

    def cleanup(self):
        """退出清理"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if self.polling_mgr:
                self.polling_mgr.stop_all()
            if hasattr(self, 'window') and self.window:
                ctx = getattr(self.window, '_ctx', None)
                if ctx and ctx.transport and ctx.transport.is_connected():
                    loop.run_until_complete(ctx.transport.disconnect())
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")


def main():
    """CLI 入口 — 启动桌面应用"""
    import argparse
    parser = argparse.ArgumentParser(description="PPCU TestBench")
    parser.add_argument("--profile", default="",
                        help="Project profile directory path")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    app = QApplication(sys.argv)
    app.setApplicationName("PPCU TestBench")
    app.setOrganizationName("PPCU")

    # 创建应用
    profile = args.profile or "profiles/ppcu_rs422"
    tui = TuiApp(profile)

    # 异步初始化
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tui.initialize())

    if tui.window:
        tui.show()
        tui.start_polling_timer()
    else:
        QMessageBox.warning(None, "初始化失败", "无法加载项目配置，请检查配置文件路径。")
        sys.exit(1)

    # 退出清理
    exit_code = app.exec()
    tui.cleanup()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
