"""
测试调度器
管理套件执行，遍历用例集，调用 CaseRunner。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ..models import SuiteDef, CaseDef, SuiteReport, CaseReport
from ..definitions import CaseStatus
from .runner import CaseRunner

logger = logging.getLogger(__name__)


class TestScheduler:
    """测试调度器——执行整套测试用例集"""

    def __init__(self, case_runner: CaseRunner):
        self._runner = case_runner
        self._callbacks: dict[str, list[Callable]] = {
            "suite_started": [],
            "case_started": [],
            "case_completed": [],
            "suite_completed": [],
        }
        self._cancel_flag = False

    async def run_suite(self, suite: SuiteDef) -> SuiteReport:
        """执行套件中的所有用例"""
        self._cancel_flag = False
        
        report = SuiteReport(
            suite_name=suite.name,
        )
        cases_to_run = self._flatten_cases(suite)
        report.total_cases = len(cases_to_run)
        
        self._emit("suite_started", suite.name)
        
        for idx, case in enumerate(cases_to_run):
            if self._cancel_flag:
                logger.info("Suite execution cancelled by user")
                break
            
            self._emit("case_started", case.name, idx, len(cases_to_run))
            
            case_report = await self._runner.run(case)
            report.cases.append(case_report)
            
            if case_report.status == CaseStatus.PASS:
                report.passed += 1
            elif case_report.status in (CaseStatus.FAIL, CaseStatus.ERROR):
                report.failed += 1
            elif case_report.status == CaseStatus.SKIP:
                report.skipped += 1
            
            self._emit("case_completed", case.name, case_report.duration_s, case_report.status)
        
        self._emit("suite_completed", suite.name, report.passed, report.failed, report.skipped)
        
        return report

    def cancel(self):
        """取消正在执行的测试套件"""
        self._cancel_flag = True

    def on(self, event: str, callback: Callable):
        """注册事件回调"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit(self, event: str, *args, **kwargs):
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Callback error on {event}: {e}")

    @staticmethod
    def _flatten_cases(suite: SuiteDef) -> list[CaseDef]:
        """扁平化套件中的用例（处理嵌套套件）"""
        cases = list(suite.cases)
        for sub in suite.suites:
            cases.extend(TestScheduler._flatten_cases(sub))
        return cases
