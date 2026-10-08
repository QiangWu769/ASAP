#!/usr/bin/env python3
"""
FRAM布局规划器 - 符号化版本（基于PC的直接备份）

为ASAP简化流程生成符号化的链接脚本。
输出包含所有槽位和ASAP_CURRENT_PC的PROVIDE语句。

输出示例：
  PROVIDE(ASAP_CURRENT_PC = 0x4400);
  PROVIDE(__SLOT_MAIN__VAR_S0 = 0x5000);
  PROVIDE(__SLOT_MAIN__VAR_S1 = 0x5002);
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# FRAM内存布局配置（MSP430FR5969）
FRAM_START = 0x4400        # FRAM起始地址
FRAM_END = 0xFF7F          # FRAM结束地址（保留中断向量区）
ASAP_CURRENT_PC_ADDR = 0x4400  # ASAP_CURRENT_PC地址（FRAM最开始，2字节）
FRAM_SLOT_START = 0x5000   # 槽位区起始地址

def sanitize_symbol_name(name: str) -> str:
    """清理字符串以生成有效的符号名"""
    name = name.upper()
    name = name.replace("::", "__")
    name = name.replace("(", "_")
    name = name.replace(")", "")
    name = name.replace(" ", "")
    name = name.replace("&", "")
    name = name.replace("#", "")
    # 确保以字母或下划线开头
    if name and name[0].isdigit():
        name = "ADDR_" + name
    return name

def calculate_slot_allocation(wid_map: Dict) -> Tuple[Dict, Dict]:
    """
    计算槽位分配（基于PC的直接备份方案，无需commit bits）
    
    Returns:
        (slot_addresses, slot_mapping)
        
        slot_addresses: {(addr, "S0"/"S1"): physical_addr}
        slot_mapping: {f"{addr}_{wid}": {"slot": "S0"/"S1", ...}}
    """
    wid_to_info = wid_map.get("wid_to_info", {})
    
    # 按地址分组WID
    addr_to_wids = defaultdict(list)
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            addr_to_wids[target_addr].append({
                "wid": wid,
                "width": info.get("width", "w"),
                "mode": info.get("mode", "")
            })
    
    print(f"[fram_layout_symbolic] 发现 {len(addr_to_wids)} 个不同的目标地址")
    
    # 分配槽位地址
    slot_addresses = {}
    slot_cursor = FRAM_SLOT_START
    
    for addr in sorted(addr_to_wids.keys()):
        wids = addr_to_wids[addr]
        
        # 确定数据宽度
        width = 2  # 默认2字节
        for wid_info in wids:
            w = wid_info.get("width", "w")
            if w == "b" or w == 1:
                width = 1
            elif w == "w" or w == 2:
                width = 2
        
        # 为该地址分配S0和S1槽位
        slot_addresses[(addr, "S0")] = slot_cursor
        slot_cursor += width
        
        slot_addresses[(addr, "S1")] = slot_cursor
        slot_cursor += width
        
        # 对齐到字边界
        if slot_cursor % 2 != 0:
            slot_cursor += 1
    
    print(f"[fram_layout_symbolic] 槽位区使用了 {slot_cursor - FRAM_SLOT_START} 字节")
    
    # 生成槽位映射（决定每个WID写入S0还是S1）
    slot_mapping = {}
    for addr, wids in addr_to_wids.items():
        for idx, wid_info in enumerate(wids):
            wid = wid_info["wid"]
            # 奇偶轮换策略
            slot_choice = "S0" if idx % 2 == 0 else "S1"
            slot_mapping[f"{addr}_{wid}"] = {
                "slot": slot_choice,
                "addr": addr,
                "wid": wid
            }
    
    return slot_addresses, slot_mapping

def generate_linker_script(
    slot_addresses: Dict,
    wid_map: Dict,
    output_path: Path
):
    """生成符号化的链接脚本（基于PC的直接备份方案）"""
    
    lines = []
    lines.append("/* ASAP FRAM Layout - Symbolic Linker Script (PC-based) */")
    lines.append("/* Auto-generated - DO NOT EDIT */")
    lines.append("")
    lines.append("/* ASAP Current PC (for recovery) */")
    lines.append(f"PROVIDE(ASAP_CURRENT_PC = 0x{ASAP_CURRENT_PC_ADDR:04X});")
    lines.append("")
    lines.append("/* Slot Definitions (S0 and S1 for each address) */")
    
    # 生成槽位定义
    wid_to_info = wid_map.get("wid_to_info", {})
    
    # 收集所有唯一的地址
    unique_addrs = set()
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            unique_addrs.add(target_addr)
    
    # 为每个地址生成S0和S1槽位
    for addr in sorted(unique_addrs):
        clean_name = sanitize_symbol_name(addr)
        
        # S0槽位
        if (addr, "S0") in slot_addresses:
            addr_val = slot_addresses[(addr, "S0")]
            lines.append(f"PROVIDE(__SLOT_{clean_name}_S0 = 0x{addr_val:04X});")
        
        # S1槽位
        if (addr, "S1") in slot_addresses:
            addr_val = slot_addresses[(addr, "S1")]
            lines.append(f"PROVIDE(__SLOT_{clean_name}_S1 = 0x{addr_val:04X});")
    
    lines.append("")
    lines.append("/* End of ASAP FRAM Layout */")
    lines.append("")
    
    # 写入文件
    with open(output_path, 'w') as f:
        f.write("\n".join(lines))
    
    print(f"[fram_layout_symbolic] ✅ 生成链接脚本: {output_path}")
    print(f"[fram_layout_symbolic]    - ASAP_CURRENT_PC at 0x{ASAP_CURRENT_PC_ADDR:04X}")
    print(f"[fram_layout_symbolic]    - {len(unique_addrs)} 个地址")
    print(f"[fram_layout_symbolic]    - {len(unique_addrs) * 2} 个槽位")

def generate_layout_report(
    slot_addresses: Dict,
    slot_mapping: Dict,
    wid_map: Dict,
    output_path: Path
):
    """生成布局报告（JSON格式，供调试和后续工具使用）"""
    
    report = {
        "asap_current_pc": f"0x{ASAP_CURRENT_PC_ADDR:04X}",
        "slot_addresses": {
            f"{addr}_{slot}": hex(phys_addr)
            for (addr, slot), phys_addr in slot_addresses.items()
        },
        "slot_mapping": slot_mapping,
        "statistics": {
            "total_addresses": len(set(addr for addr, _ in slot_addresses.keys())),
            "total_slots": len(slot_addresses),
            "slot_bytes_used": max(slot_addresses.values()) - FRAM_SLOT_START + 2 if slot_addresses else 0
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[fram_layout_symbolic] ✅ 生成布局报告: {output_path}")

def main():
    ap = argparse.ArgumentParser(description="FRAM布局规划 - 符号化版本")
    ap.add_argument("--wid-map", required=True, help="WID映射文件")
    ap.add_argument("--out-linker", default="build/fram_symbols.ld", help="输出链接脚本")
    ap.add_argument("--out-report", default="build/fram_layout_report.json", help="输出布局报告")
    args = ap.parse_args()
    
    # 加载WID映射
    wid_map_path = Path(args.wid_map)
    if not wid_map_path.exists():
        print(f"[fram_layout_symbolic] ❌ WID映射文件不存在: {wid_map_path}")
        return 1
    
    with open(wid_map_path, 'r') as f:
        wid_map = json.load(f)
    
    print(f"[fram_layout_symbolic] 加载了 {len(wid_map.get('wid_to_info', {}))} 个WID")
    
    # 计算槽位分配
    slot_addresses, slot_mapping = calculate_slot_allocation(wid_map)
    
    # 生成链接脚本
    generate_linker_script(
        slot_addresses,
        wid_map,
        Path(args.out_linker)
    )
    
    # 生成布局报告
    generate_layout_report(
        slot_addresses,
        slot_mapping,
        wid_map,
        Path(args.out_report)
    )
    
    print(f"[fram_layout_symbolic] ✅ FRAM布局规划完成")
    return 0

if __name__ == "__main__":
    exit(main())

