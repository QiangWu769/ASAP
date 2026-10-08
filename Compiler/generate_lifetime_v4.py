#!/usr/bin/env python3
"""
生成L_A[W]翻转点表 - 使用集/生命周期分析 V4

基于你的思路：分析每个地址的生命周期，生成PC范围到地址集合的映射
- 生命周期开始：地址被赋值（关键写指令）
- 生命周期结束：地址被覆盖（下一次赋值）之前最后一次读取
- 结果：[start_PC, end_PC] = {address sets}
"""

import json
import re
import argparse
from typing import Dict, List, Set, Tuple
from collections import defaultdict

def parse_asm_file(asm_file: str) -> List[Dict]:
    """解析汇编文件，提取指令信息"""
    instructions = []
    
    with open(asm_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith(';') or line.startswith('#'):
                continue
                
            # 检查是否是汇编指令
            if not any(mnemonic in line.upper() for mnemonic in ['MOV', 'BIS', 'BIC', 'XOR', 'ADD', 'SUB', 'CMP', 'JMP', 'CALL', 'RET', 'BR', 'JNZ', 'JZ', 'JNC', 'JC']):
                continue
                
            # 对于插桩后的文件，使用行号作为PC
            pc = f"line_{line_num}"
            instruction = line
            
            instructions.append({
                'line': line_num,
                'pc': pc,
                'instruction': instruction,
                'original_line': line
            })
    
    return instructions

def extract_memory_accesses(instruction: str) -> List[str]:
    """从指令中提取内存访问地址"""
    addresses = []
    
    # 匹配各种内存访问模式
    patterns = [
        r'&0x([0-9a-fA-F]+)',  # 绝对地址
        r'&([A-Z_][A-Z0-9_]*)',  # 符号地址
        r'(\d+)\(r\d+\)',  # 索引寻址
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, instruction)
        for match in matches:
            if pattern == r'&0x([0-9a-fA-F]+)':
                addresses.append(f"0x{match}")
            elif pattern == r'&([A-Z_][A-Z0-9_]*)':
                addresses.append(match)
            elif pattern == r'(\d+)\(r\d+\)':
                addresses.append(f"r1_{match}")  # 栈访问
    
    return addresses

def is_read_operation(instruction: str) -> bool:
    """判断指令是否为读取操作"""
    read_patterns = [
        r'MOV\s+&[^,]+,\s*R\d+',  # MOV &addr, R12
        r'MOV\s+&[^,]+,\s*&[^,]+',  # MOV &addr, &addr2
        r'CMP\s+&[^,]+',  # CMP &addr
        r'BIT\s+&[^,]+',  # BIT &addr
        r'TST\s+&[^,]+',  # TST &addr
    ]
    
    for pattern in read_patterns:
        if re.search(pattern, instruction, re.IGNORECASE):
            return True
    
    return False

def is_write_operation(instruction: str) -> bool:
    """判断指令是否为写入操作"""
    write_patterns = [
        r'MOV\s+[^,]+,\s*&[^,]+',  # MOV reg, &addr
        r'BIS\s+[^,]+,\s*&[^,]+',  # BIS #val, &addr
        r'BIC\s+[^,]+,\s*&[^,]+',  # BIC #val, &addr
        r'XOR\s+[^,]+,\s*&[^,]+',  # XOR reg, &addr
        r'ADD\s+[^,]+,\s*&[^,]+',  # ADD reg, &addr
        r'SUB\s+[^,]+,\s*&[^,]+',  # SUB reg, &addr
    ]
    
    for pattern in write_patterns:
        if re.search(pattern, instruction, re.IGNORECASE):
            return True
    
    return False

def get_wid_to_pc_mapping(wid_map: Dict) -> Dict[str, int]:
    """从wid_map中获取WID到PC的映射"""
    wid_to_pc = {}
    wid_to_info = wid_map.get("wid_to_info", {})
    
    for wid, info in wid_to_info.items():
        pc_str = info.get("pc", "")
        if pc_str.startswith("0x"):
            pc = int(pc_str, 16)
            wid_to_pc[wid] = pc
            print(f"[生命周期分析] WID {wid} 对应PC {pc_str} (0x{pc:04x})")
    
    return wid_to_pc

def analyze_address_lifetime(instructions: List[Dict], wid_to_pc: Dict, addr: str) -> List[Dict]:
    """分析单个地址的生命周期"""
    print(f"[生命周期分析] 分析地址 {addr} 的生命周期...")
    
    # 找到该地址的所有写操作（WID）
    write_wids = []
    for wid, pc in wid_to_pc.items():
        # 通过WID信息判断是否写入该地址
        # 这里需要从wid_map中获取更详细的信息
        write_wids.append(wid)
    
    write_wids.sort(key=lambda x: wid_to_pc[x])  # 按PC排序
    print(f"[生命周期分析] 地址 {addr} 有 {len(write_wids)} 次写操作: {write_wids}")
    
    # 分析每个写操作的生命周期
    lifetimes = []
    
    for i, write_wid in enumerate(write_wids):
        write_pc = wid_to_pc[write_wid]
        
        # 找到下一次写操作的PC
        next_write_pc = 0xFFFF  # 默认到程序结束
        if i + 1 < len(write_wids):
            next_write_wid = write_wids[i + 1]
            next_write_pc = wid_to_pc[next_write_wid]
        
        # 在本次写操作到下次写操作之间，找到最后一次读取该地址的PC
        last_read_pc = -1
        for instr in instructions:
            instr_pc = instr['line']  # 使用行号作为PC的近似
            if write_pc < instr_pc < next_write_pc:
                accesses = extract_memory_accesses(instr['instruction'])
                
                if addr in accesses and is_read_operation(instr['instruction']):
                    last_read_pc = instr_pc
                    print(f"[生命周期分析] 地址 {addr} 在WID {write_wid} 后PC {instr_pc}被读取: {instr['instruction']}")
        
        # 生命周期：从写操作到最后一次读取（如果没读取则到下次写操作）
        if last_read_pc != -1:
            lifetime_end_pc = last_read_pc
        else:
            lifetime_end_pc = next_write_pc - 1  # 到下次写操作之前
        
        lifetimes.append({
            'wid': write_wid,
            'start_pc': write_pc,
            'end_pc': lifetime_end_pc,
            'last_read_pc': last_read_pc
        })
        
        print(f"[生命周期分析] WID {write_wid}: 生命周期PC [{write_pc}, {lifetime_end_pc}], 最后读取PC: {last_read_pc}")
    
    return lifetimes

def generate_pc_ranges(lifetimes_by_addr: Dict, all_wids: List[str]) -> Dict:
    """生成PC范围到地址集合的映射"""
    print("[生命周期分析] 生成PC范围到地址集合的映射...")
    
    # 收集所有生命周期端点
    endpoints = set()
    for addr, lifetimes in lifetimes_by_addr.items():
        for lifetime in lifetimes:
            endpoints.add(lifetime['start_pc'])
            endpoints.add(lifetime['end_pc'] + 1)  # 结束点+1，因为范围是[start, end)
    
    endpoints = sorted(endpoints)
    print(f"[生命周期分析] 找到 {len(endpoints)} 个端点: {endpoints}")
    
    # 生成PC范围
    pc_ranges = {}
    
    for i in range(len(endpoints) - 1):
        start_pc = endpoints[i]
        end_pc = endpoints[i + 1] - 1
        
        # 找出在这个PC范围内alive的地址
        alive_addresses = set()
        for addr, lifetimes in lifetimes_by_addr.items():
            for lifetime in lifetimes:
                if lifetime['start_pc'] <= start_pc <= lifetime['end_pc']:
                    alive_addresses.add(addr)
                    break
        
        if alive_addresses:  # 只记录有alive地址的范围
            range_key = f"[{start_pc}, {end_pc}]"
            pc_ranges[range_key] = {
                'addresses': sorted(list(alive_addresses)),
                'alive_count': len(alive_addresses),
                'start_pc': start_pc,
                'end_pc': end_pc
            }
            print(f"[生命周期分析] 范围 {range_key}: {len(alive_addresses)} 个alive地址")
    
    return pc_ranges

def main():
    parser = argparse.ArgumentParser(description='生成L_A[W]翻转点表 V4')
    parser.add_argument('--asm', required=True, help='插桩后的汇编文件')
    parser.add_argument('--wid-map', required=True, help='WID映射文件')
    parser.add_argument('--candidates', required=True, help='候选指令文件')
    parser.add_argument('--out', required=True, help='输出文件')
    
    args = parser.parse_args()
    
    # 加载WID映射
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    # 加载候选指令
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    # 解析汇编文件
    print(f"[生命周期分析] 解析汇编文件: {args.asm}")
    instructions = parse_asm_file(args.asm)
    print(f"[生命周期分析] 解析了 {len(instructions)} 条指令")
    
    # 获取WID到PC的映射
    wid_to_pc = get_wid_to_pc_mapping(wid_map)
    print(f"[生命周期分析] 找到 {len(wid_to_pc)} 个WID到PC的映射")
    
    # 获取所有关键地址
    critical_addresses = set()
    for wid, info in wid_map.get("wid_to_info", {}).items():
        if info.get("mode") == "ABS":
            addr = info.get("target_addr", "").lower()
            if addr:
                critical_addresses.add(addr)
        elif info.get("mode") == "IDX":
            base = info.get("base", "")
            disp = info.get("disp", 0)
            if base == "r1":  # 栈访问
                critical_addresses.add(f"r1_{disp}")
    
    print(f"[生命周期分析] 发现 {len(critical_addresses)} 个关键地址: {sorted(critical_addresses)}")
    
    # 分析每个地址的生命周期
    lifetimes_by_addr = {}
    for addr in critical_addresses:
        lifetimes = analyze_address_lifetime(instructions, wid_to_pc, addr)
        lifetimes_by_addr[addr] = lifetimes
    
    # 生成PC范围到地址集合的映射
    pc_ranges = generate_pc_ranges(lifetimes_by_addr, list(wid_to_pc.keys()))
    
    # 生成报告
    report = {
        'pc_ranges': pc_ranges,
        'lifetimes_by_addr': lifetimes_by_addr,
        'summary': {
            'total_ranges': len(pc_ranges),
            'total_addresses': len(critical_addresses),
            'total_wids': len(wid_to_pc),
            'total_instructions': len(instructions)
        }
    }
    
    # 保存结果
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[生命周期分析] 生命周期分析完成")
    print(f"[生命周期分析] 生成了 {len(pc_ranges)} 个PC范围")
    print(f"[生命周期分析] 结果保存到: {args.out}")

if __name__ == '__main__':
    main()
