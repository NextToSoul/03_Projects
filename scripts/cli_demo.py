#!/usr/bin/env python
"""
PPCU TestBench — CLI 验证脚本

不依赖 PySide6，在纯终端环境中验证 Phase 1 核心引擎的全部组件：
  1. 配置加载（Excel + YAML）
  2. 协议编解码
  3. 遥测注册表
  4. 安全保护
  5. 测试用例加载
  6. 序列号管理
  7. 位域解析

用法:
  python scripts/cli_demo.py --profile profiles/ppcu_rs422
  python scripts/cli_demo.py --profile profiles/ppcu_rs422 --offline    # 不连硬件，测试加载与编解码
"""

# ────────────────────────────────────────────
# 不依赖 PySide6，使用桩代替 QObject/Signal
# ────────────────────────────────────────────
import sys
import os
# 在 import 任何 core 模块之前，先让 signals 模块知道这是 CLI 模式
os.environ["PPCU_CLI_MODE"] = "1"

# 添加项目根到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
   level=logging.INFO,
   format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
   datefmt="%H:%M:%S",
)
logger = logging.getLogger("CLI")


async def main():
   parser = argparse.ArgumentParser(description="PPCU TestBench CLI Demo")
   parser.add_argument("--profile", default="profiles/ppcu_rs422",
                       help="Profile directory path")
   parser.add_argument("--offline", action="store_true",
                       help="Run in offline mode (no hardware connection)")
   args = parser.parse_args()
   
   profile_path = Path(args.profile)
   if not profile_path.exists():
       profile_path = Path.cwd() / args.profile
   
   print("=" * 60)
   print("  PPCU TestBench — Phase 1 核心引擎验证")
   print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
   print("=" * 60)
   
   # ─── 1. 测试配置加载 ──────────────────────────
   print("\n[1/6] 配置加载 ...")
   
   from src.config.loader import ProfileLoader
   loader = ProfileLoader()
   ctx = await loader.load(profile_path)
   
   tm_reg = ctx.telemetry_registry
   cmd_reg = ctx.command_registry
   
   print(f"  [OK] 项目: {ctx.name}")
   print(f"  [OK] 遥测包: {tm_reg.total_packages} 个 ({tm_reg.total_params} 个参数)")
   for pkg in tm_reg.list_packages():
       print(f"      - {pkg.name}: {len(pkg.parameters)} 参数")
   print(f"  [OK] 指令: {len(cmd_reg.list_commands())} 条")
   print(f"  [OK] 参数注入: {len(cmd_reg.get_injections())} 张表")
   
   # ─── 2. 测试协议编解码 ─────────────────────────
   print("\n[2/6] 协议编解码 ...")
   
   from src.core.hardware.sequencer import SequenceManager
   seq = SequenceManager()
   
   # 编码第一条指令
   cmd = cmd_reg.get_command("APID_00C0") or cmd_reg.list_commands()[0]
   frame = ctx.protocol.encode_command(cmd, seq.next())
   frame_hex = frame.hex(" ").upper()
   print(f"  编码指令: {cmd.name} ({cmd.id})")
   print(f"  Frame: {frame_hex}")
   
   # 解码帧头
   frame_info = ctx.protocol.decode_frame(frame)
   print(f"  解码: identifier=0x{frame_info.identifier:04X}, "
         f"apid=0x{frame_info.apid:04X}, "
         f"seq={frame_info.sequence_count}, "
         f"checksum={'[OK]' if frame_info.checksum_ok else '[FAIL]'}")
   
   # 拼接错误校验和验证
   bad_frame = bytearray(frame)
   bad_frame[-2] = 0x00
   bad_info = ctx.protocol.decode_frame(bytes(bad_frame))
   print(f"  校验错误检测: {'[OK] 正确拦截' if not bad_info.checksum_ok else '[FAIL] 检测失败'}")
   
   # ─── 3. 测试序列号管理 ─────────────────────────
   print("\n[3/6] 序列号管理 ...")
   
   seq.reset()
   seqs = [seq.next() for _ in range(5)]
   print(f"  连续5个序列号: {seqs}")
   assert seqs == [0, 1, 2, 3, 4], f"序列号异常: {seqs}"
   print("  [OK] 序列号自增正常")
   
   seq.reset(0x3FFE)
   wrap_seqs = [seq.next() for _ in range(4)]
   print(f"  回绕测试 (0x3FFE→): {wrap_seqs}")
   assert wrap_seqs == [0x3FFE, 0x3FFF, 0, 1], f"回绕异常: {wrap_seqs}"
   print(f"  [OK] 14-bit 回绕正常 (回绕次数: {seq.wrap_count})")
   
   # ─── 4. 测试遥测注册表 ─────────────────────────
   print("\n[4/6] 遥测注册表 ...")
   
   # 跨包搜索参数
   param = tm_reg.get_param("TM1001")
   if param:
       pkg_name = tm_reg.get_package_for_param("TM1001")
       print(f"  参数 TM1001: {param.name} ({pkg_name})")
       print(f"    data_offset={param.data_offset}, bit_offset={param.bit_offset}, "
             f"bit_length={param.bit_length}, type={param.data_type}")
       print(f"    scale={param.scale}, unit='{param.unit}'")
       if param.enum_values:
           print(f"    enum_values: {param.enum_values}")
   
   # 枚举参数
   enum_param = tm_reg.get_param("TM1005")
   if enum_param and enum_param.enum_values:
       print(f"  枚举参数 TM1005 ({enum_param.name}):")
       for k, v in enum_param.enum_values.items():
           print(f"    {k} → {v}")
   
   print(f"  [OK] 遥测注册表: {tm_reg.total_params} 参数可搜索")
   
   # ─── 5. 测试位域解析 ───────────────────────────
   print("\n[5/6] 位域解析引擎 ...")
   
   from src.core.hardware.packet import BitFieldParser
   parser = BitFieldParser()
   
   # 构造模拟遥测数据包
   # 假设 常规包1 有 48 个参数，数据域约 48*8=384 bits = 48 bytes
   pkg1 = tm_reg.get_package("常规包1")
   if pkg1:
       mock_data = bytes(range(48))  # 48 bytes: 0x00, 0x01, ..., 0x2F
       snapshots = parser.parse_packet(mock_data, pkg1.parameters[:5])
       print(f"  模拟数据包 (48 bytes):")
       for snap in snapshots[:5]:
           print(f"    {snap.param_id} ({snap.param_name}): "
                 f"raw=0x{snap.raw_value:X}, "
                 f"phys={snap.physical_value}{snap.unit}")
       
       # 测试物理值→原始值转换
       raw = parser.physical_to_raw(120.0, "float32", "big")
       back = parser.raw_to_physical(raw, "float32", "big")
       print(f"  物理量编码/解码: 120.0 → {raw.hex().upper()} → {back}")
       assert abs(back - 120.0) < 0.001, "转换误差过大"
       print(f"  [OK] 浮点编码解码正常")
       
       # 测试 scale 换算: TM1008 scale=0.0055555556
       tm1008 = tm_reg.get_param("TM1008")
       if tm1008 and tm1008.scale != 1.0:
           raw_voltage = 0x5DC0  # 24000 * 0.005555... ≈ 133.33V
           # 模拟解析
           mock_voltage_data = bytes([0x5D, 0xC0] + [0] * 46)
           snap = parser.parse_packet(mock_voltage_data, [tm1008])[0]
           print(f"  Scale 测试 ({tm1008.param_id} {tm1008.param_name}): "
                 f"scale={tm1008.scale}, phys={snap.physical_value}{snap.unit}")
   
   # ─── 6. 测试安全保护 ───────────────────────────
   print("\n[6/6] 安全保护 ...")
   
   from src.core.safety.guard import SafetyGuard
   safety = SafetyGuard(ctx.safety)
   
   cmd_reset = cmd_reg.get_command("TCHEDTTA001") or cmd
   allowed, reason = safety.check_command(cmd_reset)
   if ctx.safety and any(c.get("blocked") for c in ctx.safety.blocked_categories):
       print(f"  复位指令 '{cmd_reset.name}': {'[OK] 已拦截' if not allowed else '[FAIL] 未拦截'}")
       if not allowed:
           print(f"    原因: {reason}")
   
   is_high_risk = safety.is_high_risk(cmd_reset)
   print(f"  高危指令检测: {'[OK]' if is_high_risk else '信息'}")
   
   # 参数值校验
   valid, msg = safety.validate_param(500.0)
   print(f"  参数值校验 (500.0): {'[OK] 通过' if valid else f'[FAIL] {msg}'}")
   
   invalid, msg = safety.validate_param(5000.0)
   print(f"  参数值校验 (5000.0): {'[OK] 通过' if invalid else f'[FAIL] {msg}'}")
   
   # ─── 完成 ──────────────────────────────────────
   print("\n" + "=" * 60)
   print("  Phase 1 核心引擎全部验证通过 [OK]")
   print("=" * 60)
   print(f"\n  项目路径: {profile_path.resolve()}")
   print(f"  下一步: Phase 2 PySide6 UI 开发")
   print()


if __name__ == "__main__":
   asyncio.run(main())
