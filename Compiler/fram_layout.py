#!/usr/bin/env python3
"""
FRAM布局规划脚本

实现ASAP的FRAM内存布局规划：
1. 为每个地址分配S0和S1槽位
2. 为每个(地址,WID)对分配提交位C[A,WID]
3. 生成符号定义文件(linker script format)
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

# FRAM区域定义（与linker script一致）
ASAP_SLOTS_START = 0x6400
ASAP_SLOTS_SIZE = 0x1000  # 4KB
ASAP_COMMITS_START = 0x7400
ASAP_COMMITS_SIZE = 0x0400  # 1KB

def collect_addresses_from_wid_map(wid_map: Dict) -> Set[str]:
    """从WID映射中收集所有写入地址"""
    addresses = set()
    wid_to_info = wid_map.get("wid_to_info", {})
    
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            addresses.add(target_addr)
    
    return addresses

def collect_wid_address_pairs(wid_map: Dict, candidates: List[Dict]) -> List[tuple]:
    """收集所有(地址,WID)对"""
    pairs = []
    wid_to_info = wid_map.get("wid_to_info", {})
    
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "")
        if target_addr:
            pairs.append((target_addr, wid))
    
    return pairs

def allocate_slots(addresses: Set[str]) -> tuple:
    """为每个地址分配S0和S1槽位"""
    s0_slots = {}
    s1_slots = {}
    
    current_offset = 0
    sorted_addrs = sorted(addresses)
    
    for addr in sorted_addrs:
        # 每个地址需要2字节(MSP430是16位)
        s0_addr = ASAP_SLOTS_START + current_offset
        s1_addr = s0_addr + 2
        
        s0_slots[addr] = f"0x{s0_addr:04X}"
        s1_slots[addr] = f"0x{s1_addr:04X}"
        
        current_offset += 4  # S0(2字节) + S1(2字节)
        
        if current_offset >= ASAP_SLOTS_SIZE:
            print(f"[fram_layout] 警告: SLOTS区域不足，已分配{len(s0_slots)}个地址")
            break
    
    print(f"[fram_layout] 分配槽位: {len(s0_slots)}个地址，使用{current_offset}字节")
    return s0_slots, s1_slots

def allocate_commit_bits(pairs: List[tuple]) -> Dict[str, str]:
    """为每个(地址,WID)对分配提交位"""
    commit_bits = {}
    
    current_offset = 0
    sorted_pairs = sorted(pairs, key=lambda x: (x[0], x[1]))
    
    for addr, wid in sorted_pairs:
        commit_addr = ASAP_COMMITS_START + current_offset
        commit_bits[wid] = f"0x{commit_addr:04X}"
        
        current_offset += 1  # 每个提交位1字节
        
        if current_offset >= ASAP_COMMITS_SIZE:
            print(f"[fram_layout] 警告: COMMITS区域不足，已分配{len(commit_bits)}个WID")
            break
    
    print(f"[fram_layout] 分配提交位: {len(commit_bits)}个WID，使用{current_offset}字节")
    return commit_bits

def compute_slot_mapping(pairs: List[tuple], s0_slots: Dict, s1_slots: Dict) -> Dict:
    """计算slot_of(A,WID)映射：为每个(A,WID)决定使用S0还是S1"""
    slot_mapping = {}
    
    # 统计每个地址的WID列表
    addr_to_wids = {}
    for addr, wid in pairs:
        if addr not in addr_to_wids:
            addr_to_wids[addr] = []
        addr_to_wids[addr].append(wid)
    
    # 对每个地址，按WID顺序交替分配S0/S1
    for addr, wids in addr_to_wids.items():
        sorted_wids = sorted(wids, key=lambda x: int(x.replace("W", "")))
        for i, wid in enumerate(sorted_wids):
            slot_choice = i % 2  # 0=S0, 1=S1
            slot_mapping[f"{addr}_{wid}"] = {
                "address": addr,
                "wid": wid,
                "slot": "S0" if slot_choice == 0 else "S1",
                "slot_address": s0_slots.get(addr, "") if slot_choice == 0 else s1_slots.get(addr, "")
            }
    
    print(f"[fram_layout] 槽位映射: {len(slot_mapping)}个(地址,WID)对")
    return slot_mapping

def generate_linker_symbols(s0_slots: Dict, s1_slots: Dict, commit_bits: Dict, output_path: Path):
    """生成链接器符号定义文件"""
    lines = []
    lines.append("/* Auto-generated FRAM layout symbols */\n")
    lines.append("/* S0 Slots */\n")
    
    for addr, s0_addr in sorted(s0_slots.items()):
        # 清理地址以生成合法的符号名
        # 索引寻址: "accel_sample::3(r1)" -> "ACCEL_SAMPLE__3_R1"
        # 绝对地址: "0x0120" -> "0120"
        clean_addr = addr.replace("0x", "").replace("(", "_").replace(")", "").replace(" ", "").replace("::", "__").upper()
        lines.append(f"PROVIDE(__RS_S0_{clean_addr} = {s0_addr});\n")
    
    lines.append("\n/* S1 Slots */\n")
    for addr, s1_addr in sorted(s1_slots.items()):
        clean_addr = addr.replace("0x", "").replace("(", "_").replace(")", "").replace(" ", "").replace("::", "__").upper()
        lines.append(f"PROVIDE(__RS_S1_{clean_addr} = {s1_addr});\n")
    
    lines.append("\n/* Commit Bits */\n")
    for wid, commit_addr in sorted(commit_bits.items()):
        lines.append(f"PROVIDE(__RS_COMMIT_{wid} = {commit_addr});\n")
    
    with open(output_path, 'w') as f:
        f.writelines(lines)
    
    print(f"[fram_layout] 生成符号文件: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="FRAM layout planning")
    parser.add_argument("--wid-map", required=True, help="WID mapping JSON")
    parser.add_argument("--candidates", required=True, help="Normalized candidates JSON")
    parser.add_argument("--out-report", required=True, help="Output report JSON")
    parser.add_argument("--out-symbols", required=True, help="Output linker symbols")
    args = parser.parse_args()
    
    # 加载输入数据
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    print(f"[fram_layout] 开始FRAM布局规划")
    print(f"[fram_layout] WID总数: {len(wid_map.get('wid_to_info', {}))}")
    print(f"[fram_layout] 候选指令: {len(candidates)}")
    
    # 从WID映射中收集所有地址
    addresses = collect_addresses_from_wid_map(wid_map)
    print(f"[fram_layout] 唯一地址数: {len(addresses)}")
    
    # 收集(地址,WID)对
    pairs = collect_wid_address_pairs(wid_map, candidates)
    print(f"[fram_layout] (地址,WID)对数: {len(pairs)}")
    
    # 分配槽位
    s0_slots, s1_slots = allocate_slots(addresses)
    
    # 分配提交位
    commit_bits = allocate_commit_bits(pairs)
    
    # 计算槽位映射
    slot_mapping = compute_slot_mapping(pairs, s0_slots, s1_slots)
    
    # 生成报告
    report = {
        "addresses": list(addresses),
        "pairs_count": len(pairs),
        "s0_slots": s0_slots,
        "s1_slots": s1_slots,
        "commit_bits": commit_bits,
        "slot_mapping": slot_mapping,
        "statistics": {
            "total_addresses": len(addresses),
            "total_pairs": len(pairs),
            "slots_used_bytes": len(addresses) * 4,
            "commits_used_bytes": len(commit_bits),
            "slots_capacity": ASAP_SLOTS_SIZE,
            "commits_capacity": ASAP_COMMITS_SIZE
        }
    }
    
    # 保存报告
    with open(args.out_report, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"[fram_layout] 生成报告: {args.out_report}")
    
    # 生成链接器符号
    generate_linker_symbols(s0_slots, s1_slots, commit_bits, Path(args.out_symbols))
    
    print(f"[fram_layout] FRAM布局规划完成")

if __name__ == "__main__":
    main()
