 <!-- 此文件由 Codex 自动加载，提供项目初始化上下文 -->
 
 # PPCU TestBench
 
 航天 PPCU 自动化测试平台。
 PySide6 + asyncio, CCSDS 协议, TCP→RS422。
 
 ## 快速参考
 
 - **设计文档**: docs/2026-06-10-ppcu-testbench-design.md
 - **项目配置**: profiles/ppcu_rs422/profile.yaml
 - **入口文件**: src/app.py (UI) / scripts/cli_demo.py (CLI)
 - **数据模型**: src/core/models.py (所有 dataclass)
 - **硬件抽象**: src/core/hardware/transport.py, protocol.py
 - **遥测系统**: src/core/telemetry/registry.py, cache.py, poller.py
 - **测试引擎**: src/core/engine/executor.py, runner.py, scheduler.py
 - **配置加载**: src/config/loader.py, src/config/loaders/excel_loader.py
 - **安全保护**: src/core/safety/guard.py
 
 ## 开发状态
 
 - Phase 0 ✅: 脚手架、设计文档、Git、项目配置
 - Phase 1 🔄: 核心引擎（数据模型 ✅ 定义、加载器 ✅ 硬件抽象 ✅ 遥测系统 ✅ 安全模块 ✅ 引擎调度 ✅ CLI验证脚本）
 - Phase 2-5: 待开发
 
 ## 当前 Phase 1 文件清单
 
 - src/core/definitions.py — 枚举常量
 - src/core/models.py — 数据模型
 - src/core/signals.py — 事件总线
 - src/core/hardware/transport.py — Transport 接口 + TCPTransport
 - src/core/hardware/protocol.py — ProtocolCodec + CCSDSCodec
 - src/core/hardware/packet.py — BitFieldParser
 - src/core/hardware/sequencer.py — SequenceManager
 - src/core/telemetry/registry.py — TelemetryRegistry + CommandRegistry
 - src/core/telemetry/cache.py — TelemetryCache
 - src/core/telemetry/poller.py — PollingManager
 - src/core/engine/executor.py — StepExecutor
 - src/core/engine/runner.py — CaseRunner
 - src/core/engine/scheduler.py — TestScheduler
 - src/core/engine/project_switch.py — ProjectSwitcher
 - src/core/safety/guard.py — SafetyGuard
 - src/config/loader.py — ProfileLoader
 - src/config/loaders/excel_loader.py — ExcelLoader
