"""
ProfileLoader — 项目配置加载器
将 profiles/<project>/ 目录下的 YAML + Excel 文件加载为运行时 ProjectContext。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

from ..core.models import (
    ProfileConfig, SafetyConfig, ProjectContext,
    TelemetryPackageDef, CommandDef, SuiteDef, CaseDef, StepDef,
    ConditionCheck, TimePointCheck,
)
from ..core.definitions import TransportType, ProtocolType
from ..core.hardware.transport import Transport, TCPTransport
from ..core.hardware.protocol import ProtocolCodec, CCSDSCodec
from ..core.hardware.sequencer import SequenceManager
from ..core.telemetry.registry import TelemetryRegistry, CommandRegistry
from ..core.telemetry.cache import TelemetryCache
from ..core.telemetry.poller import PollingManager
from ..core.safety.guard import SafetyGuard
from .loaders.excel_loader import ExcelLoader

logger = logging.getLogger(__name__)


class ProfileLoader:
    """项目配置加载器"""

    def __init__(self):
        self._profile_dir: Path | None = None

    async def load(self, project_path: str | Path) -> ProjectContext:
        """完整加载一个项目配置"""
        self._profile_dir = Path(project_path)
        if not self._profile_dir.exists():
            raise FileNotFoundError(f"Profile directory not found: {project_path}")
        
        ctx = ProjectContext()
        
        # 1. 加载 profile.yaml
        profile = self._load_profile_yaml()
        ctx.profile = profile
        ctx.name = profile.name
        
        # 2. 创建 Transport
        transport = self._create_transport(profile)
        ctx.transport = transport
        
        # 3. 创建 ProtocolCodec
        protocol = self._create_protocol(profile)
        ctx.protocol = protocol
        
        # 4. 创建序列号管理器
        seq_mgr = SequenceManager()
        
        # 5. 创建遥测缓存
        cache = TelemetryCache()
        
        # 6. 加载遥测和指令注册表
        tm_registry, cmd_defs = self._load_protocol_tables(profile)
        ctx.telemetry_registry = tm_registry
        
        cmd_reg = CommandRegistry()
        cmd_reg.add_commands(cmd_defs)
        ctx.command_registry = cmd_reg
        
        # 7. 加载注入配置
        if profile.injections:
            for inj in ExcelLoader.load_injections([
                {"name": i.get("name", ""), "excel_path": i.get("excel_path", "")}
                for i in profile.injections
            ]):
                cmd_reg.add_injection(inj)
        
        # 8. 创建 PollingManager
        poller = PollingManager(transport, protocol, seq_mgr, cache)
        poller.set_registries(tm_registry, cmd_reg)
        
        for pkg_def in tm_registry.list_packages():
            for pkg_meta in profile.telemetry_packages:
                if pkg_meta.get("name") == pkg_def.name:
                    pkg_def.command_id = pkg_meta.get("command_id", "")
                    pkg_def.frame_type = pkg_meta.get("frame_type", "slow")
                    pkg_def.default_poll = pkg_meta.get("default_poll", "disabled")
                    pkg_def.poll_interval_s = pkg_meta.get("poll_interval_s", 1.0)
                    break
            poller.register_package(pkg_def)
        
        # 9. 加载安全策略
        safety_config = self._load_safety(profile)
        ctx.safety = SafetyConfig(
            enabled=safety_config.get("enabled", True),
            blocked_categories=safety_config.get("block_categories", []),
            high_risk_commands=safety_config.get("high_risk_commands", []),
            validate_param_range=safety_config.get("param_injection", {}).get("validate_range", True),
            max_injection_value=safety_config.get("param_injection", {}).get("max_value_per_injection", 600.0),
        )
        
        # 10. 加载测试用例
        cases_dir = self._profile_dir / "cases"
        if cases_dir.exists():
            ctx.test_suites = self._load_cases(cases_dir)
        
        logger.info(f"Profile loaded: {ctx.name} "
                    f"({tm_registry.total_packages} packages, "
                    f"{tm_registry.total_params} params, "
                    f"{len(cmd_reg.list_commands())} commands)")
        
        return ctx

    def _load_profile_yaml(self) -> ProfileConfig:
        if yaml is None:
            raise ImportError("PyYAML is required")
        path = self._profile_dir / "profile.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        profile = ProfileConfig(
            name=data.get("name", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            created=data.get("created", ""),
            transport_type=data.get("transport", {}).get("type", "tcp"),
            transport_config=data.get("transport", {}).get("config", {}),
            protocol_type=data.get("protocol", {}).get("type", "ccsds"),
            protocol_config=data.get("protocol", {}).get("config", {}),
            telemetry_packages=data.get("telemetry", {}).get("packages", []),
        )
        
        telemetry_cfg = data.get("telemetry", {})
        if telemetry_cfg.get("excel_path"):
            profile.telemetry_excel_path = str(self._profile_dir / telemetry_cfg["excel_path"])
        if telemetry_cfg.get("patches_path"):
            profile.telemetry_patches_path = str(self._profile_dir / telemetry_cfg["patches_path"])
        
        commands_cfg = data.get("commands", {})
        if commands_cfg.get("excel_path"):
            profile.commands_excel_path = str(self._profile_dir / commands_cfg["excel_path"])
        
        injections_cfg = data.get("injections", [])
        for inj in injections_cfg:
            if inj.get("excel_path"):
                inj["excel_path"] = str(self._profile_dir / inj["excel_path"])
        profile.injections = injections_cfg
        
        safety_cfg = data.get("safety", {})
        if safety_cfg.get("policy_path"):
            profile.safety_policy_path = str(self._profile_dir / safety_cfg["policy_path"])
        profile.auto_connect = data.get("safety", {}).get("auto_connect", False)
        
        return profile

    def _create_transport(self, profile: ProfileConfig) -> Transport:
        t = profile.transport_type
        if t == "tcp":
            return TCPTransport(profile.transport_config)
        raise ValueError(f"Unsupported transport type: {t}")

    def _create_protocol(self, profile: ProfileConfig) -> ProtocolCodec:
        t = profile.protocol_type
        if t == "ccsds":
            return CCSDSCodec(profile.protocol_config)
        raise ValueError(f"Unsupported protocol type: {t}")

    def _load_protocol_tables(self, profile: ProfileConfig) -> tuple:
        tm_registry = TelemetryRegistry()
        commands = []
        
        if profile.telemetry_excel_path and Path(profile.telemetry_excel_path).exists():
            packages = ExcelLoader.load_telemetry_packages(profile.telemetry_excel_path)
            for pkg in packages:
                tm_registry.add_package(pkg)
        
        if profile.commands_excel_path and Path(profile.commands_excel_path).exists():
            commands = ExcelLoader.load_commands(profile.commands_excel_path)
        
        return tm_registry, commands

    def _load_safety(self, profile: ProfileConfig) -> dict:
        if not profile.safety_policy_path or not Path(profile.safety_policy_path).exists():
            return {}
        with open(profile.safety_policy_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_cases(self, cases_dir: Path) -> list[SuiteDef]:
        suites = []
        for yaml_file in sorted(cases_dir.glob("*.yaml")):
            suite = self._load_case_yaml(yaml_file)
            if suite:
                suites.append(suite)
        return suites

    def _load_case_yaml(self, path: Path) -> SuiteDef | None:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return None
            
            if "cases" in data:
                suite = SuiteDef(
                    name=data.get("name", path.stem),
                    description=data.get("description", ""),
                )
                for case_ref in data["cases"]:
                    if isinstance(case_ref, str):
                        ref_path = path.parent / case_ref
                        sub = self._load_case_yaml(ref_path)
                        if sub:
                            suite.cases.extend(sub.cases)
                    elif isinstance(case_ref, dict):
                        case = self._parse_case(case_ref)
                        if case:
                            suite.cases.append(case)
                return suite
            elif "steps" in data:
                suite = SuiteDef(name=data.get("suite", "default"))
                case = self._parse_case(data)
                if case:
                    suite.cases.append(case)
                return suite
            return None
        except Exception as e:
            logger.error(f"Failed to load case file {path}: {e}")
            return None

    def _parse_case(self, data: dict) -> CaseDef | None:
        try:
            steps = []
            for s in data.get("steps", []):
                step = StepDef(
                    id=s.get("id", ""),
                    name=s.get("name", ""),
                    type=s.get("action", "send_command"),
                    timeout_s=float(s.get("timeout_s", 10)),
                    on_fail=s.get("on_fail", "stop"),
                    command_id=s.get("command", ""),
                    param_value=s.get("param_value", ""),
                    package=s.get("package", ""),
                    trigger_command=s.get("trigger_command", ""),
                    trigger_param=s.get("trigger_param", ""),
                    duration_s=float(s.get("duration_s", 1)),
                )
                for c in s.get("checks", []):
                    step.checks.append(ConditionCheck(
                        param_id=c.get("parameter", ""),
                        operator=c.get("operator", "equals"),
                        expected_value=str(c.get("expected", "")),
                        tolerance=float(c["tolerance"]) if c.get("tolerance") else None,
                    ))
                for tp in s.get("timepoints", []):
                    offset_str = tp.get("offset", "+0s")
                    offset = float(offset_str.replace("s", "").replace("+", ""))
                    for c in tp.get("checks", []):
                        step.timepoints.append(TimePointCheck(
                            offset_seconds=offset,
                            package=tp.get("package", ""),
                            param_id=c.get("parameter", ""),
                            operator=c.get("operator", "equals"),
                            expected_value=str(c.get("expected", "")),
                            tolerance=float(c["tolerance"]) if c.get("tolerance") else None,
                        ))
                steps.append(step)
            
            prereqs = []
            for c in data.get("prerequisites", []):
                prereqs.append(ConditionCheck(
                    param_id=c.get("parameter", ""),
                    operator=c.get("operator", "equals"),
                    expected_value=str(c.get("expected", "")),
                ))
            
            return CaseDef(
                name=data.get("name", "Unnamed"),
                description=data.get("description", ""),
                tags=data.get("tags", []),
                steps=steps,
                params=data.get("params", {}),
                prerequisites=prereqs,
            )
        except Exception as e:
            logger.error(f"Failed to parse case: {e}")
            return None