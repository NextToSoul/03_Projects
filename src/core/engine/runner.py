"""
用例运行器
执行单条用例的所有步骤，管理步骤间的跳转和失败处理。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..models import (
    CaseDef, StepDef, CaseReport, StepReport,
)
from ..definitions import StepStatus, CaseStatus, OnFailAction
from .executor import StepExecutor

logger = logging.getLogger(__name__)


class CaseRunner:
    """单用例执行器"""

    def __init__(self, executor: StepExecutor, status_callback: Any = None):
        self._executor = executor
        self._status_callback = status_callback  # for UI signal forwarding

    async def run(self, case: CaseDef) -> CaseReport:
        """执行一条用例"""
        report = CaseReport(
            name=case.name,
            id=case.name,
            tags=case.tags,
            status="running",
        )
        t0 = time.monotonic()
        
        # 检查前置条件
        if case.prerequisites:
            prereq_ok = await self._check_prerequisites(case.prerequisites)
            if not prereq_ok:
                report.status = "skip"
                report.fail_reason = "前置条件不满足"
                report.duration_s = time.monotonic() - t0
                return report
        
        # 按序执行步骤
        step_index = 0
        step_count = len(case.steps)
        
        while step_index < step_count:
            step = case.steps[step_index]
            
            # 发射状态
            self._emit_status(case.name, step.id, step.name, "running")
            
            # 执行
            step_report = await self._executor.execute(step)
            report.steps.append(step_report)
            
            # 发射结果
            self._emit_status(case.name, step.id, step.name, step_report.status)
            
            # 处理失败
            if step_report.status in ("fail", "error", "blocked"):
                action = step.on_fail or "stop"
                
                if action == "stop":
                    report.status = "fail"
                    report.fail_reason = step_report.detail or f"步骤 {step.id} 失败"
                    report.fail_detail = step_report.detail
                    break
                elif action == "continue":
                    step_index += 1
                    continue
                elif action == "goto":
                    # 跳转到指定步骤
                    try:
                        step_index = next(
                            i for i, s in enumerate(case.steps)
                            if s.id == step.target_step
                        )
                    except StopIteration:
                        step_index += 1
                    continue
            
            step_index += 1
        
        # 如果没有失败，标记为通过
        if report.status == "running":
            report.status = "pass"
        
        report.duration_s = time.monotonic() - t0
        return report

    async def _check_prerequisites(self, checks: list) -> bool:
        """检查前置条件"""
        # 简化实现：对于简单的前置条件，直接尝试获取遥测并判断
        # 更复杂的实现需要等待条件满足
        try:
            for check in checks:
                snapshot = self._executor._cache.get_param_value(check.param_id)
                if snapshot:
                    actual = snapshot.physical_value
                    expected = self._executor._parse_expected(check.expected_value)
                    if not self._executor._evaluate(actual, expected, check.operator):
                        return False
            return True
        except Exception:
            return False

    def _emit_status(self, case: str, step_id: str, step_name: str, status: str):
        if self._status_callback:
            try:
                self._status_callback(case, step_id, step_name, status)
            except Exception:
                pass
