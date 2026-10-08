#!/usr/bin/env python3
"""
基于 WID 的生命周期分析 - 不需要真实 PC！

核心思想：
1. 从插桩汇编中提取每个地址的读写操作（按行号顺序）
2. 分析每个 WID 之后哪些地址是活跃的
3. 输出格式：{ "W1": ["0x2001", "0x2002"], "W2": [...], ... }
4. 不需要真实 PC，只需要 WID 的相对顺序！
"""

import json
import re
import argparse
from typing import Dict, List, Set
from collections import defaultdict

def parse_instrumented_asm(asm_file: str) -> List[Dict]:
    """解析插桩后的汇编，提取指令和WID标记"""
    instructions = []
    current_line = 0
    
    with open(asm_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            
            # 跳过空行和注释
            if not stripped or stripped.startswith(';') or stripped.startswith('.') or stripped.startswith('#'):
                continue
            if stripped.endswith(':'):  # 标签
                continue
            
            # 检查是否是 WID 标记
            wid_match = re.search(r'ASAP\s+(?:backup|commit)\s+for\s+(W\d+)', line, re.IGNORECASE)
            
            # 提取地址引用
            addresses = re.findall(r'&(0x[0-9a-fA-F]+)', line)
            addresses = [addr.lower() for addr in addresses]
            
            # 判断读写
            is_write = False
            is_read = False
            
            if addresses:
                # 简化判断：如果地址在逗号后面，通常是写
                parts = stripped.split(',')
                if len(parts) >= 2:
                    if any(addr in parts[-1].lower() for addr in addresses):
                        is_write = True
                    if any(addr in parts[0].lower() for addr in addresses):
                        is_read = True
            
            instructions.append({
                'line': line_num,
                'text': stripped,
                'addresses': addresses,
                'wid': wid_match.group(1) if wid_match else None,
                'is_write': is_write,
                'is_read': is_read
            })
            current_line = line_num
    
    return instructions

def build_wid_to_line_map(instructions: List[Dict], wid_map: Dict) -> Dict[str, int]:
    """建立 WID 到行号的映射"""
    wid_to_line = {}
    
    for inst in instructions:
        if inst['wid']:
            wid_to_line[inst['wid']] = inst['line']
    
    # 补充没找到的 WID（使用 wid_map 的信息）
    for wid in wid_map.get("wid_to_info", {}).keys():
        if wid not in wid_to_line:
            # 使用一个默认值
            wid_to_line[wid] = 999999
    
    return wid_to_line

def analyze_address_reads(instructions: List[Dict], addr: str) -> List[int]:
    """找到地址的所有读取位置（行号）"""
    read_lines = []
    
    for inst in instructions:
        if addr in inst['addresses'] and inst['is_read']:
            read_lines.append(inst['line'])
    
    return sorted(read_lines)

def compute_alive_addresses_for_wid(wid: str, wid_map: Dict, 
                                    wid_to_line: Dict[str, int],
                                    instructions: List[Dict]) -> Set[str]:
    """
    计算某个 WID 执行后哪些地址是活跃的
    
    规则：
    1. 遍历所有地址
    2. 如果地址在此 WID 之前或此处被写入，且在下次被写入前有读取，则活跃
    """
    wid_line = wid_to_line.get(wid, 999999)
    alive_addrs = set()
    
    # 按地址分组 WID
    addr_to_wids = defaultdict(list)
    wid_to_info = wid_map.get("wid_to_info", {})
    
    for w, info in wid_to_info.items():
        target_addr = info.get("target_addr", "").lower()
        if target_addr:
            addr_to_wids[target_addr].append(w)
    
    # 对每个地址分析
    for addr, wids in addr_to_wids.items():
        # 按行号排序这些 WID
        wids_sorted = sorted(wids, key=lambda w: wid_to_line.get(w, 999999))
        
        # 找到当前 WID 位置
        # 找出最后一个写入该地址的 WID（在当前 WID 之前或就是当前 WID）
        last_write_wid = None
        for w in wids_sorted:
            w_line = wid_to_line.get(w, 999999)
            if w_line <= wid_line:
                last_write_wid = w
            else:
                break
        
        if not last_write_wid:
            continue  # 这个地址还没被写入
        
        # 找到下一个写入该地址的 WID
        next_write_wid = None
        next_write_line = 999999
        for w in wids_sorted:
            w_line = wid_to_line.get(w, 999999)
            if w_line > wid_line:
                next_write_wid = w
                next_write_line = w_line
                break
        
        # 在 [wid_line, next_write_line) 范围内查找读取
        has_read = False
        for inst in instructions:
            if wid_line < inst['line'] < next_write_line:
                if addr in inst['addresses'] and inst['is_read']:
                    has_read = True
                    break
        
        # 如果有读取，则该地址是活跃的
        if has_read:
            alive_addrs.add(addr)
    
    return alive_addrs

def main():
    parser = argparse.ArgumentParser(description='基于 WID 的生命周期分析（无需真实 PC）')
    parser.add_argument('--asm', required=True, help='插桩后的汇编文件')
    parser.add_argument('--wid-map', required=True, help='WID映射文件')
    parser.add_argument('--out', required=True, help='输出文件')
    
    args = parser.parse_args()
    
    # 加载 WID 映射
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    wid_to_info = wid_map.get("wid_to_info", {})
    print(f"[生命周期分析] 加载了 {len(wid_to_info)} 个 WID")
    
    # 解析汇编
    print(f"[生命周期分析] 解析汇编文件: {args.asm}")
    instructions = parse_instrumented_asm(args.asm)
    print(f"[生命周期分析] 解析了 {len(instructions)} 条指令")
    
    # 建立 WID 到行号的映射
    wid_to_line = build_wid_to_line_map(instructions, wid_map)
    print(f"[生命周期分析] 找到 {len(wid_to_line)} 个 WID 的位置")
    
    # 为每个 WID 计算活跃地址
    wid_to_alive = {}
    alive_stats = []
    
    for wid in sorted(wid_to_info.keys(), key=lambda w: int(w[1:])):
        alive_addrs = compute_alive_addresses_for_wid(wid, wid_map, wid_to_line, instructions)
        wid_to_alive[wid] = sorted(list(alive_addrs))
        alive_stats.append(len(alive_addrs))
        
        if len(alive_addrs) > 0:
            print(f"[生命周期分析] {wid}: {len(alive_addrs)} 个活跃地址")
    
    # 统计
    print(f"\n[生命周期分析] ===== 统计 =====")
    print(f"总 WID 数: {len(wid_to_alive)}")
    if alive_stats:
        print(f"最小活跃数: {min(alive_stats)}")
        print(f"最大活跃数: {max(alive_stats)}")
        print(f"平均活跃数: {sum(alive_stats) / len(alive_stats):.1f}")
    
    # 保存结果（兼容旧格式）
    # 生成假的 pc_ranges（用 WID 编号代替 PC）
    pc_ranges = {}
    for wid, addrs in wid_to_alive.items():
        wid_num = int(wid[1:])
        # 使用 WID 编号作为虚拟 PC
        pc_ranges[f"[{wid_num}, {wid_num}]"] = {
            'addresses': addrs,
            'alive_count': len(addrs),
            'start_pc': wid_num,
            'end_pc': wid_num,
            'wid': wid
        }
    
    report = {
        'pc_ranges': pc_ranges,
        'wid_to_alive': wid_to_alive,  # 新格式：直接 WID → 地址列表
        'summary': {
            'total_wids': len(wid_to_alive),
            'min_alive': min(alive_stats) if alive_stats else 0,
            'max_alive': max(alive_stats) if alive_stats else 0,
            'avg_alive': sum(alive_stats) / len(alive_stats) if alive_stats else 0
        }
    }
    
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[生命周期分析] 结果保存到: {args.out}")

if __name__ == '__main__':
    main()





































