#!/usr/bin/env python3
"""
基于反汇编文件的精确生命周期分析

从最终固件的反汇编中：
1. 提取所有内存访问指令及其真实 PC
2. 找到每个地址的所有读取位置
3. 计算精确的生命周期：从 WID NextPC 到最后一次读取
"""

import json
import re
import argparse
from typing import Dict, List, Set, Tuple
from collections import defaultdict

def parse_disasm_instruction(line: str) -> Tuple[int, str, List[str]]:
    """解析反汇编指令行
    
    格式: "    861e:	d2 42 df 23 	mov.b	&0x23df,&0x501a	;0x23df"
    返回: (pc_int, mnemonic, addresses)
    """
    # 匹配地址
    match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f ]+)\s+(\S+)\s+(.*)', line)
    if not match:
        return None, None, []
    
    pc_hex = match.group(1)
    pc_int = int(pc_hex, 16)
    mnemonic = match.group(3).lower()
    operands = match.group(4)
    
    # 提取所有绝对地址 &0xXXXX
    addresses = re.findall(r'&(0x[0-9a-f]+)', operands)
    
    return pc_int, mnemonic, addresses

def is_read_operation(mnemonic: str, operands: str, addr: str) -> bool:
    """判断是否是读取操作
    
    规则：地址出现在源操作数位置
    例如：mov &0x2001, r12  <- 读取 0x2001
         mov r12, &0x2001  <- 写入 0x2001
    """
    # 简化判断：如果地址是第一个操作数，通常是读取
    parts = operands.split(',')
    if len(parts) < 2:
        return False
    
    src = parts[0].strip()
    return addr in src

def extract_memory_accesses_from_disasm(disasm_file: str) -> Dict[str, Dict]:
    """从反汇编中提取所有内存访问
    
    返回: {
        '0x2001': {
            'reads': [pc1, pc2, ...],
            'writes': [pc3, pc4, ...]  # 来自 WID
        }
    }
    """
    accesses = defaultdict(lambda: {'reads': [], 'writes': []})
    
    with open(disasm_file, 'r') as f:
        for line in f:
            pc_int, mnemonic, addresses = parse_disasm_instruction(line)
            
            if pc_int is None or not addresses:
                continue
            
            # 检查每个地址
            for addr in addresses:
                addr_lower = addr.lower()
                
                # 判断是读还是写
                if is_read_operation(mnemonic, line, addr):
                    accesses[addr_lower]['reads'].append(pc_int)
                # 注意：写操作由 WID 确定，不从这里提取
    
    # 排序
    for addr_data in accesses.values():
        addr_data['reads'].sort()
    
    return dict(accesses)

def analyze_lifetime_with_reads(wid_map: Dict, wid_to_nextpc: Dict, 
                                 mem_accesses: Dict[str, Dict]) -> Dict[str, List[Dict]]:
    """基于真实读取操作的生命周期分析"""
    
    lifetimes_by_addr = {}
    wid_to_info = wid_map.get("wid_to_info", {})
    
    # 按地址分组 WID
    addr_to_wids = defaultdict(list)
    for wid, info in wid_to_info.items():
        target_addr = info.get("target_addr", "").lower()
        if target_addr and wid in wid_to_nextpc:
            addr_to_wids[target_addr].append(wid)
    
    print(f"[生命周期分析] 找到 {len(addr_to_wids)} 个被写入的地址")
    
    # 分析每个地址
    for addr, wids in addr_to_wids.items():
        # 按 NextPC 排序
        wids.sort(key=lambda w: wid_to_nextpc[w])
        
        # 获取该地址的所有读取 PC
        read_pcs = mem_accesses.get(addr, {}).get('reads', [])
        
        lifetimes = []
        
        for i, wid in enumerate(wids):
            nextpc = wid_to_nextpc[wid]
            
            # 生命周期开始：WID 的 NextPC
            start_pc = nextpc
            
            # 找到下一个写入的 PC
            if i + 1 < len(wids):
                next_write_pc = wid_to_nextpc[wids[i + 1]]
            else:
                next_write_pc = 0xFFFF
            
            # 在 [start_pc, next_write_pc) 范围内找到最后一次读取
            last_read_pc = -1
            for read_pc in read_pcs:
                if start_pc <= read_pc < next_write_pc:
                    last_read_pc = read_pc
            
            # 生命周期结束
            if last_read_pc != -1:
                # 找到了真实的最后读取
                end_pc = last_read_pc
            else:
                # 没有读取，生命周期到下一次写入前（或程序结束）
                end_pc = next_write_pc - 1 if next_write_pc != 0xFFFF else 0xFFFF
            
            lifetimes.append({
                'wid': wid,
                'start_pc': start_pc,
                'end_pc': end_pc,
                'last_read_pc': last_read_pc if last_read_pc != -1 else end_pc,
                'read_count': len([r for r in read_pcs if start_pc <= r <= end_pc])
            })
            
            status = "有读取" if last_read_pc != -1 else "无读取"
            print(f"[生命周期分析] {addr} WID {wid}: [{start_pc}, {end_pc}], {status}, 读取次数: {lifetimes[-1]['read_count']}")
        
        if lifetimes:
            lifetimes_by_addr[addr] = lifetimes
    
    return lifetimes_by_addr

def generate_pc_ranges(lifetimes_by_addr: Dict) -> Dict:
    """生成PC范围到地址集合的映射"""
    print("[生命周期分析] 生成PC范围...")
    
    # 收集所有端点
    endpoints = set()
    for addr, lifetimes in lifetimes_by_addr.items():
        for lt in lifetimes:
            endpoints.add(lt['start_pc'])
            endpoints.add(lt['end_pc'] + 1)
    
    endpoints = sorted(endpoints)
    
    # 生成PC范围
    pc_ranges = {}
    
    for i in range(len(endpoints) - 1):
        start_pc = endpoints[i]
        end_pc = endpoints[i + 1] - 1
        
        # 找出alive的地址
        alive_addresses = set()
        for addr, lifetimes in lifetimes_by_addr.items():
            for lt in lifetimes:
                if lt['start_pc'] <= start_pc <= lt['end_pc']:
                    alive_addresses.add(addr)
                    break
        
        if alive_addresses:
            range_key = f"[{start_pc}, {end_pc}]"
            pc_ranges[range_key] = {
                'addresses': sorted(list(alive_addresses)),
                'alive_count': len(alive_addresses),
                'start_pc': start_pc,
                'end_pc': end_pc
            }
    
    return pc_ranges

def main():
    parser = argparse.ArgumentParser(description='基于反汇编的精确生命周期分析')
    parser.add_argument('--disasm', required=True, help='反汇编文件')
    parser.add_argument('--wid-map', required=True, help='WID映射文件')
    parser.add_argument('--nextpc', required=True, help='NextPC表')
    parser.add_argument('--out', required=True, help='输出文件')
    
    args = parser.parse_args()
    
    # 加载 WID 映射
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    # 加载 NextPC 表
    with open(args.nextpc, 'r') as f:
        nextpc_data = json.load(f)
        nextpc_table = nextpc_data.get('nextpc_table', nextpc_data)
    
    # 转换 NextPC 为整数
    wid_to_nextpc = {}
    for wid, nextpc_str in nextpc_table.items():
        if nextpc_str.startswith("0x"):
            wid_to_nextpc[wid] = int(nextpc_str, 16)
    
    print(f"[生命周期分析] 加载了 {len(wid_to_nextpc)} 个 WID 的 NextPC")
    
    # 提取内存访问
    print(f"[生命周期分析] 解析反汇编文件: {args.disasm}")
    mem_accesses = extract_memory_accesses_from_disasm(args.disasm)
    print(f"[生命周期分析] 找到 {len(mem_accesses)} 个被访问的地址")
    
    # 显示一些读取统计
    total_reads = sum(len(data['reads']) for data in mem_accesses.values())
    print(f"[生命周期分析] 总读取操作: {total_reads}")
    
    # 分析生命周期
    lifetimes_by_addr = analyze_lifetime_with_reads(wid_map, wid_to_nextpc, mem_accesses)
    
    # 生成 PC 范围
    pc_ranges = generate_pc_ranges(lifetimes_by_addr)
    
    # 统计
    alive_counts = [r['alive_count'] for r in pc_ranges.values()]
    print(f"\n[生命周期分析] ===== 统计 =====")
    print(f"PC范围数: {len(pc_ranges)}")
    if alive_counts:
        print(f"最小alive数: {min(alive_counts)}")
        print(f"最大alive数: {max(alive_counts)}")
        print(f"平均alive数: {sum(alive_counts) / len(alive_counts):.1f}")
    else:
        print(f"最小/最大/平均alive数: 0")
    
    # 保存结果
    report = {
        'pc_ranges': pc_ranges,
        'lifetimes_by_addr': lifetimes_by_addr,
        'summary': {
            'total_ranges': len(pc_ranges),
            'total_addresses': len(lifetimes_by_addr),
            'total_wids': len(wid_to_nextpc),
            'min_alive': min(alive_counts) if alive_counts else 0,
            'max_alive': max(alive_counts) if alive_counts else 0,
            'avg_alive': sum(alive_counts) / len(alive_counts) if alive_counts else 0
        }
    }
    
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[生命周期分析] 结果保存到: {args.out}")

if __name__ == '__main__':
    main()

