#!/usr/bin/env python3
"""
生成ASAP运行时元数据的C代码

将NextPC表、生命周期数据、WriteWIDs等嵌入到固件的.rodata段
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List

def generate_nextpc_array(nextpc_table: Dict, wid_map: Dict = None) -> List[str]:
    """生成NextPC数组"""
    lines = []
    
    # 按WID排序
    wids = sorted(nextpc_table.keys(), key=lambda x: int(x.replace("W", "")))
    
    lines.append("/* NextPC表: NextPC[WID] = 继续执行地址 */")
    lines.append("const uint16_t ASAP_NextPC[] = {")
    
    for i, wid in enumerate(wids):
        addr = nextpc_table[wid]
        lines.append(f"    {addr},  // {wid}")
    
    lines.append("};")
    lines.append(f"const uint16_t ASAP_NextPC_Count = {len(wids)};")
    
    # 如果nextpc_table为空，从wid_map获取总WID数
    total_wids = len(wids)
    if total_wids == 0 and wid_map:
        total_wids = len(wid_map.get("wid_to_info", {}))
        print(f"[generate_metadata_c] 警告: NextPC表为空，从wid_map获取WID总数: {total_wids}")
    
    lines.append(f"const uint16_t _total_wids = {total_wids};  /* For bootloader */")
    lines.append("")
    
    return lines

def generate_lifetime_tables(lifetime_data: Dict) -> List[str]:
    """生成生命周期数据表"""
    lines = []
    
    pc_ranges = lifetime_data.get("pc_ranges", {})
    
    lines.append("/* 生命周期数据：PC范围 -> 活跃地址集合 */")
    
    ranges = []
    for range_key, range_data in sorted(pc_ranges.items()):
        start_pc = range_data.get("start_pc", 0)
        end_pc = range_data.get("end_pc", 0)
        alive_count = range_data.get("alive_count", 0)
        ranges.append((start_pc, end_pc, alive_count))
    
    lines.append("const PCRange ASAP_PC_Ranges[] = {")
    for start, end, count in ranges:
        lines.append(f"    {{{start}, {end}, {count}}},")
    lines.append("};")
    lines.append(f"const uint16_t ASAP_PC_Range_Count = {len(ranges)};")
    lines.append("")
    
    return lines

def generate_writewids_table(wid_map: Dict) -> List[str]:
    """生成WriteWIDs表（每个地址的写序列）"""
    lines = []
    
    wid_to_info = wid_map.get("wid_to_info", {})
    
    # 按地址分组WID
    from collections import defaultdict
    addr_to_wids = defaultdict(list)
    
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            wid_num = int(wid.replace("W", ""))
            addr_to_wids[target_addr].append(wid_num)
    
    lines.append("/* WriteWIDs: 每个地址的写序列（用于查找last_write） */")
    
    # 生成每个地址的WID数组
    for addr, wids in sorted(addr_to_wids.items()):
        # 清理地址名用作变量名
        addr_clean = addr.replace("0x", "0x").replace("::", "_").replace("(", "_").replace(")", "")
        lines.append(f"const uint8_t wids_{addr_clean}[] = {{{', '.join(map(str, sorted(wids)))}}};")
    
    lines.append("")
    
    # 生成地址表
    lines.append("const AddrWriteSeq ASAP_WriteWIDs[] = {")
    for addr, wids in sorted(addr_to_wids.items()):
        addr_hex = addr if addr.startswith("0x") else f"/* {addr} */"
        addr_clean = addr.replace("0x", "0x").replace("::", "_").replace("(", "_").replace(")", "")
        
        # 尝试解析地址
        if addr.startswith("0x"):
            addr_val = addr
        else:
            addr_val = "0x0000"  # 索引寻址暂时用0
        
        lines.append(f"    {{{addr_val}, {len(wids)}, wids_{addr_clean}}},")
    
    lines.append("};")
    lines.append(f"const uint16_t ASAP_WriteWIDs_Count = {len(addr_to_wids)};")
    lines.append("")
    
    return lines

def generate_slot_mapping(fram_layout: Dict) -> List[str]:
    """生成slot_of(A,W)映射表"""
    lines = []
    
    slot_mapping = fram_layout.get("slot_mapping", {})
    
    lines.append("/* Slot映射: slot_of(A, W) -> S0/S1 */")
    
    # 按WID排序
    mappings = []
    for key, info in slot_mapping.items():
        wid = info.get("wid", "")
        slot = info.get("slot", "S0")
        if wid:
            wid_num = int(wid.replace("W", ""))
            slot_num = 0 if slot == "S0" else 1
            mappings.append((wid_num, slot_num))
    
    lines.append("const WIDSlot ASAP_SlotMapping[] = {")
    for wid_num, slot_num in sorted(mappings):
        lines.append(f"    {{{wid_num}, {slot_num}}},")
    lines.append("};")
    lines.append(f"const uint16_t ASAP_SlotMapping_Count = {len(mappings)};")
    lines.append("")
    
    return lines

def generate_header(output_path: Path) -> List[str]:
    """生成头文件"""
    lines = []
    
    guard = output_path.stem.upper() + "_H"
    
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}")
    lines.append("")
    lines.append("#include <stdint.h>")
    lines.append("")
    lines.append("/* ASAP运行时元数据 - Auto-generated */")
    lines.append("")
    lines.append("extern const uint16_t ASAP_NextPC[];")
    lines.append("extern const uint16_t ASAP_NextPC_Count;")
    lines.append("")
    lines.append("typedef struct {")
    lines.append("    uint16_t start_pc;")
    lines.append("    uint16_t end_pc;")
    lines.append("    uint8_t alive_count;")
    lines.append("} PCRange;")
    lines.append("")
    lines.append("extern const PCRange ASAP_PC_Ranges[];")
    lines.append("extern const uint16_t ASAP_PC_Range_Count;")
    lines.append("")
    lines.append("typedef struct {")
    lines.append("    uint16_t addr;")
    lines.append("    uint8_t wid_count;")
    lines.append("    const uint8_t* wids;")
    lines.append("} AddrWriteSeq;")
    lines.append("")
    lines.append("extern const AddrWriteSeq ASAP_WriteWIDs[];")
    lines.append("extern const uint16_t ASAP_WriteWIDs_Count;")
    lines.append("")
    lines.append("typedef struct {")
    lines.append("    uint8_t wid;")
    lines.append("    uint8_t slot;")
    lines.append("} WIDSlot;")
    lines.append("")
    lines.append("extern const WIDSlot ASAP_SlotMapping[];")
    lines.append("extern const uint16_t ASAP_SlotMapping_Count;")
    lines.append("")
    lines.append(f"#endif // {guard}")
    lines.append("")
    
    return lines

def main():
    ap = argparse.ArgumentParser(description="生成ASAP运行时元数据C代码")
    ap.add_argument("--nextpc", required=True, help="NextPC表JSON")
    ap.add_argument("--lifetime", required=True, help="生命周期数据JSON")
    ap.add_argument("--wid-map", required=True, help="WID映射JSON")
    ap.add_argument("--fram-layout", required=True, help="FRAM布局JSON")
    ap.add_argument("--out-c", default="build/asap_metadata.c", help="输出C文件")
    ap.add_argument("--out-h", default="build/asap_metadata.h", help="输出头文件")
    args = ap.parse_args()
    
    # 加载数据
    print("[generate_metadata_c] 加载数据...")
    
    with open(args.nextpc, 'r') as f:
        nextpc_data = json.load(f)
        nextpc_table = nextpc_data.get("nextpc_table", {})
    
    with open(args.lifetime, 'r') as f:
        lifetime_data = json.load(f)
    
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    with open(args.fram_layout, 'r') as f:
        fram_layout = json.load(f)
    
    print(f"[generate_metadata_c] NextPC: {len(nextpc_table)} 条目")
    print(f"[generate_metadata_c] 生命周期: {len(lifetime_data.get('pc_ranges', {}))} PC范围")
    print(f"[generate_metadata_c] WID: {len(wid_map.get('wid_to_info', {}))} 个")
    
    # 生成C代码
    c_lines = []
    c_lines.append("/* ASAP运行时元数据 - Auto-generated */")
    c_lines.append("#include <stdint.h>")
    c_lines.append(f'#include "{Path(args.out_h).name}"')
    c_lines.append("")
    
    c_lines.extend(generate_nextpc_array(nextpc_table, wid_map))  # 传入wid_map以获取total_wids
    c_lines.extend(generate_lifetime_tables(lifetime_data))
    c_lines.extend(generate_writewids_table(wid_map))
    c_lines.extend(generate_slot_mapping(fram_layout))
    
    # 写入C文件
    output_c = Path(args.out_c)
    with open(output_c, 'w') as f:
        f.write("\n".join(c_lines))
    
    print(f"[generate_metadata_c] ✅ 生成C文件: {output_c}")
    
    # 生成头文件
    h_lines = generate_header(Path(args.out_h))
    
    output_h = Path(args.out_h)
    with open(output_h, 'w') as f:
        f.write("\n".join(h_lines))
    
    print(f"[generate_metadata_c] ✅ 生成头文件: {output_h}")
    print(f"[generate_metadata_c] 数据将被嵌入到固件的.rodata段")
    
    return 0

if __name__ == "__main__":
    exit(main())
