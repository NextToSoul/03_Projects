"""
步骤执行器
根据步骤类型调用不同的执行路径，每种步骤类型是一个独立方法。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..models import (
    StepDef, StepReport, CommandDef,
    ConditionCheck, TimePointCheck,
    TelemetrySnapshot, TelemetryUpdate,
)
from ..definitions import StepStatus, OnFailAction, PollMode
from ..hardware.transport import Transport
from ..hardware.protocol import ProtocolCodec
from ..hardware.sequencer import SequenceManager
from ..telemetry.cache import TelemetryCache
from ..telemetry.registry import TelemetryRegistry, CommandRegistry
from ..safety.guard import SafetyGuard

logger = logging.getLogger(__name__)


class StepExecutor:
    """步骤执行器——执行所有步骤类型"""

    def __init__(
        self,
        transport: Transport,
        protocol: ProtocolCodec,
        seq_mgr: SequenceManager,
        telemetry_cache: TelemetryCache,
        telemetry_registry: TelemetryRegistry,
        command_registry: CommandRegistry,
        safety: SafetyGuard,
    ):
        self._transport = transport
        self._protocol = protocol
        self._seq = seq_mgr
        self._cache = telemetry_cache
        self._tm_registry = telemetry_registry
        self._cmd_registry = command_registry
        self._safety = safety

    async def execute(self, step: StepDef) -> StepReport:
        """执行单个步骤，返回执行报告"""
        # 捕获配置快照
        config_snapshot = self._capture_config(step)
        t0 = time.monotonic()
        
        try:
            if step.type == "send_command":
                result = await self._send_command(step)
            elif step.type == "verify_telemetry":
                result = await self._verify_telemetry(step)
            elif step.type == "wait_for_condition":
                result = await self._wait_for_condition(step)
            elif step.type == "timing_verification":
                result = await self._timing_verification(step)
            elif step.type == "delay":
                result = await self._delay(step)
            else:
                result = StepReport(
                    status="error",
                    detail=f"Unknown step type: {step.type}"
                )
        except Exception as e:
            logger.exception(f"Step {step.id} execution error")
            result = StepReport(status="error", detail=str(e))
        
        duration = time.monotonic() - t0
        result.id = step.id
        result.name = step.name
        result.type = step.type
        result.duration_s = duration
        result.config_snapshot = config_snapshot
        return result

    async def _send_command(self, step: StepDef) -> StepReport:
        """发送指令"""
        cmd = self._cmd_registry.get_command(step.command_id)
        if not cmd:
            return StepReport(status="error", detail=f"Unknown command: {step.command_id}")
        
        # 安全检查
        allowed, reason = self._safety.check_command(cmd)
        if not allowed:
            return StepReport(status="blocked", detail=f"安全拦截: {reason}")
        
        # 编码并发送
        params = {"value": step.param_value} if step.param_value else None
        seq = self._seq.next()
        frame = self._protocol.encode_command(cmd, seq, params)
        await self._transport.send(frame)
        
        return StepReport(status="pass", detail=f"指令已发送: {cmd.name}")

    async def _verify_telemetry(self, step: StepDef) -> StepReport:
        """验证遥测参数"""
        if not step.checks:
            return StepReport(status="error", detail="验证步骤没有配置检查条件")
        
        # 获取遥测快照
        snapshots = await self._get_telemetry(step)
        if not snapshots:
            return StepReport(status="error", detail="无法获取遥测数据")
        
        # 逐一检查条件
        snapshot_map = {s.param_id: s for s in snapshots}
        failed_checks = []
        
        for check in step.checks:
            snap = snapshot_map.get(check.param_id)
            if not snap:
                failed_checks.append(f"{check.param_id}: 未找到遥测参数")
                continue
            
            actual = snap.physical_value
            expected = self._parse_expected(check.expected_value)
            
            if not self._evaluate(actual, expected, check.operator, check.tolerance):
                failed_checks.append(
                    f"{check.param_id}: 预期={expected}, 实际={actual}"
                )
        
        if failed_checks:
            return StepReport(
                status="fail",
                detail="; ".join(failed_checks),
                telemetry_snapshots=snapshots,
            )
        
        return StepReport(status="pass", telemetry_snapshots=snapshots)

    async def _wait_for_condition(self, step: StepDef) -> StepReport:
        """等待条件满足（轮询遥测直到超时）"""
        deadline = time.monotonic() + step.timeout_s
        last_snapshots = []
        
        while time.monotonic() < deadline:
            snapshots = await self._get_telemetry(step)
            if snapshots:
                last_snapshots = snapshots
                snapshot_map = {s.param_id: s for s in snapshots}
                
                all_pass = True
                for check in step.checks:
                    snap = snapshot_map.get(check.param_id)
                    if not snap:
                        all_pass = False
                        break
                    actual = snap.physical_value
                    expected = self._parse_expected(check.expected_value)
                    if not self._evaluate(actual, expected, check.operator, check.tolerance):
                        all_pass = False
                        break
                
                if all_pass:
                    return StepReport(status="pass", telemetry_snapshots=snapshots)
            
            await asyncio.sleep(step.poll_interval_s)
        
        return StepReport(
            status="fail",
            detail=f"超时 {step.timeout_s}s 后条件仍未满足",
            telemetry_snapshots=last_snapshots,
        )

    async def _timing_verification(self, step: StepDef) -> StepReport:
        """时序验证：发触发指令，在多个时间点检查遥测"""
        if not step.timepoints:
            return StepReport(status="error", detail="时序验证步骤没有配置时间点")
        
        # 1. 发送触发指令
        cmd = self._cmd_registry.get_command(step.trigger_command)
        if cmd:
            params = {"value": step.trigger_param} if step.trigger_param else None
            seq = self._seq.next()
            frame = self._protocol.encode_command(cmd, seq, params)
            await self._transport.send(frame)
        
        t0 = time.monotonic()
        deadline = t0 + step.timeout_s
        
        # 2. 对每个时间点记录检查状态
        tp_results: list[dict] = []
        for tp in step.timepoints:
            tp_results.append({
                "offset": tp.offset_seconds,
                "param_id": tp.param_id,
                "expected": tp.expected_value,
                "operator": tp.operator,
                "tolerance": tp.tolerance,
                "actual": None,
                "result": "pending",
            })
        
        # 3. 轮询遥测，检查时间点
        while time.monotonic() < deadline:
            elapsed = time.monotonic() - t0
            
            # 检查是否有到期的未检查时间点
            for tp_result in tp_results:
                if tp_result["result"] != "pending":
                    continue
                if elapsed >= tp_result["offset"]:
                    # 获取该时间点的遥测值
                    snapshots = self._cache.get_latest(step.package) if step.package else None
                    if not snapshots:
                        snapshots = await self._get_telemetry(step)
                    if snapshots:
                        snapshot_map = {s.param_id: s for s in snapshots}
                        snap = snapshot_map.get(tp_result["param_id"])
                        if snap:
                            actual = snap.physical_value
                            expected = self._parse_expected(tp_result["expected"])
                            tp_result["actual"] = str(actual)
                            if self._evaluate(actual, expected, tp_result["operator"], tp_result["tolerance"]):
                                tp_result["result"] = "pass"
                            else:
                                tp_result["result"] = "fail"
            
            # 全部检查完毕则退出
            if all(t["result"] != "pending" for t in tp_results):
                break
            
            await asyncio.sleep(0.5)
        
        # 4. 汇总结果
        failed_tps = [t for t in tp_results if t["result"] == "fail"]
        pending_tps = [t for t in tp_results if t["result"] == "pending"]
        
        if failed_tps:
            details = "; ".join(
                f"+{t['offset']}s {t['param_id']}: 预期={t['expected']}, 实际={t['actual']}"
                for t in failed_tps
            )
            return StepReport(status="fail", detail=details)
        
        if pending_tps:
            return StepReport(status="fail", detail=f"超时: {len(pending_tps)}个时间点未检查")
        
        return StepReport(status="pass")

    async def _delay(self, step: StepDef) -> StepReport:
        """延时等待"""
        await asyncio.sleep(step.duration_s)
        return StepReport(status="pass", detail=f"等待 {step.duration_s}s")

    async def _get_telemetry(self, step: StepDef) -> list[TelemetrySnapshot] | None:
        """获取遥测数据——优先查缓存，需要时发查询"""
        # 优先从缓存读取
        if step.package:
            snapshots = self._cache.get_latest(step.package)
            if snapshots:
                return snapshots
        
        # 缓存没有，按需查询
        if step.package:
            pkg = self._tm_registry.get_package(step.package)
            if pkg and pkg.command_id:
                cmd = self._cmd_registry.get_command(pkg.command_id)
                if cmd:
                    seq = self._seq.next()
                    frame = self._protocol.encode_command(cmd, seq)
                    await self._transport.send(frame)
                    resp = await self._transport.recv(timeout_s=3.0)
                    if resp:
                        from ..hardware.packet import BitFieldParser
                        parser = BitFieldParser()
                        header_size = 6
                        payload = resp[header_size:-2]
                        snapshots = parser.parse_packet(payload, pkg.parameters)
                        self._cache.update_package(step.package, snapshots)
                        return snapshots
        
        return None

    def _capture_config(self, step: StepDef) -> dict:
        """捕获步骤配置快照（用于报告）"""
        base = {
            "step_type": step.type,
            "timeout_s": step.timeout_s,
            "on_fail": step.on_fail,
        }
        
        if step.type == "send_command":
            cmd = self._cmd_registry.get_command(step.command_id)
            base["command_id"] = step.command_id
            base["command_name"] = cmd.name if cmd else ""
            base["command_code"] = cmd.command_code if cmd else ""
            base["parameter_value"] = step.param_value
        elif step.type in ("verify_telemetry", "wait_for_condition"):
            base["package"] = step.package
            base["checks"] = [
                {"param_id": c.param_id, "operator": c.operator,
                 "expected": c.expected_value, "tolerance": c.tolerance}
                for c in step.checks
            ]
        elif step.type == "timing_verification":
            base["trigger_command"] = step.trigger_command
            base["trigger_param"] = step.trigger_param
            base["timepoints"] = [
                {"offset": f"+{tp.offset_seconds}s", "param_id": tp.param_id,
                 "operator": tp.operator, "expected": tp.expected_value,
                 "tolerance": tp.tolerance}
                for tp in step.timepoints
            ]
        elif step.type == "delay":
            base["duration_s"] = step.duration_s
        
        return base

    @staticmethod
    def _parse_expected(value: str) -> float | str:
        """解析预期值字符串"""
        try:
            return float(value) if "." in value else int(value, 0)
        except (ValueError, TypeError):
            return value

    @staticmethod
    def _evaluate(
        actual: object,
        expected: object,
        operator: str,
        tolerance: float | None = None,
    ) -> bool:
        """评估条件"""
        try:
            a = float(actual) if not isinstance(actual, (int, float)) else float(actual)
            e = float(expected) if not isinstance(expected, (int, float)) else float(expected)
        except (TypeError, ValueError):
            return str(actual) == str(expected)
        
        if operator in ("equals", "="):
            if tolerance:
                return abs(a - e) <= tolerance
            return a == e
        elif operator in ("approx", "≈"):
            tol = tolerance or 0.01
            return abs(a - e) <= tol
        elif operator in ("greater_than", ">"):
            return a > e
        elif operator in ("less_than", "<"):
            return a < e
        elif operator in (">=", "≥"):
            return a >= e
        elif operator in ("<=", "≤"):
            return a <= e
        elif operator == "between":
            # expected is "min,max"
            try:
                parts = str(expected).split(",")
                return float(parts[0]) <= a <= float(parts[1])
            except (ValueError, IndexError):
                return False
        elif operator == "not_equal":
            return a != e
        
        return str(actual) == str(expected)
