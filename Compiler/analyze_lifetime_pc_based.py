#!/usr/bin/env python3
"""
基于PC的生命周期分析工具

从反汇编中提取关键写的真实PC，分析每个地址的生命周期，
输出PC范围到活跃地址集合的映射。

输入：
  - wid_map.json: 关键写的信息
  - firmware.elf: 编译后的固件（用于反汇编）

输出：
  - lifetime_pc.json: {pc: [alive_addrs], ...} 或 PC范围映射
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

def disassemble_firmware(elf_path: Path) -> List[Dict]:
    """
    反汇编固件，提取所有指令
    
    Returns:
        [{"pc": "0x9d7e", "mnemonic": "mov", "operands": "r12, &0x1234"}, ...]
    """
    try:
        result = subprocess.run(
            ["msp430-elf-objdump", "-d", str(elf_path)],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[analyze_lifetime_pc] 反汇编失败: {e}")
        return []
    
    instructions = []
    # 匹配格式：    9d7e:	4c 92 34 12 	mov	r12,	&0x1234
    pattern = re.compile(r'^\s*([0-9a-f]+):\s+[0-9a-f\s]+\s+(\w+)(?:\.b|\.w)?\s*(.*)$')
    
    for line in result.stdout.split('\n'):
        m = pattern.match(line)
        if m:
            pc_str = m.group(1)
            mnemonic = m.group(2).lower()
            operands = m.group(3).strip()
            
            instructions.append({
                "pc": f"0x{pc_str}",
                "mnemonic": mnemonic,
                "operands": operands
            })
    
    print(f"[analyze_lifetime_pc] 反汇编得到 {len(instructions)} 条指令")
    return instructions

def find_critical_write_pcs(instructions: List[Dict], wid_map: Dict) -> Dict[str, str]:
    """
    从反汇编中找到每个关键写的真实PC
    
    方法：查找 "MOV R0, &0x4400" 指令（0x4400=ASAP_CURRENT_PC），这条指令紧跟在关键写之后
    
    Returns:
        {wid: pc_of_save_instruction}
    """
    wid_to_pc = {}
    
    # 找到所有 "mov r0, &0x4400" 的指令（ASAP_CURRENT_PC = 0x4400）
    save_pc_instructions = []
    for inst in instructions:
        ops = inst['operands'].lower()
        # 匹配：r0, &0x4400 或 r0,	&0x4400
        if inst['mnemonic'] == 'mov' and 'r0' in ops and '0x4400' in ops:
            save_pc_instructions.append(inst['pc'])
    
    print(f"[analyze_lifetime_pc] 找到 {len(save_pc_instructions)} 个保存PC的指令")
    
    # 从wid_map获取WID总数
    wid_count = len(wid_map.get('wid_to_info', {}))
    
    # 为每个WID分配一个保存PC指令的地址
    # 假设顺序一致（插桩顺序 = WID顺序）
    wids = sorted(wid_map.get('wid_to_info', {}).keys(), key=lambda x: int(x.replace('W', '')))
    
    for idx, wid in enumerate(wids):
        if idx < len(save_pc_instructions):
            wid_to_pc[wid] = save_pc_instructions[idx]
    
    print(f"[analyze_lifetime_pc] 映射了 {len(wid_to_pc)} 个WID到PC")
    return wid_to_pc

def analyze_address_lifetimes(
    instructions: List[Dict],
    wid_map: Dict,
    wid_to_pc: Dict[str, str]
) -> Dict[str, Set[str]]:
    """
    分析每个PC位置的活跃地址集合
    
    Returns:
        {pc: {addr1, addr2, ...}}
    """
    wid_to_info = wid_map.get('wid_to_info', {})
    
    # 构建地址到WID的映射（一个地址可能被多个WID写入）
    addr_to_writes = defaultdict(list)
    for wid, info in wid_to_info.items():
        target_addr = info.get('target_addr', '')
        if target_addr and wid in wid_to_pc:
            pc = wid_to_pc[wid]
            addr_to_writes[target_addr].append({
                'wid': wid,
                'pc': pc,
                'pc_int': int(pc, 16)
            })
    
    # 对每个地址的写入按PC排序
    for addr in addr_to_writes:
        addr_to_writes[addr] = sorted(addr_to_writes[addr], key=lambda x: x['pc_int'])
    
    # 构建PC索引（所有保存PC指令的地址，按顺序）
    all_pcs = sorted(set(wid_to_pc.values()), key=lambda x: int(x, 16))
    pc_to_int = {pc: int(pc, 16) for pc in all_pcs}
    
    # 对每个PC，确定哪些地址是活跃的
    pc_to_alive = {}
    
    for pc in all_pcs:
        pc_int = pc_to_int[pc]
        alive_addrs = set()
        
        # 对每个地址，检查是否在当前PC活跃
        for addr, writes in addr_to_writes.items():
            # 找到该地址在当前PC之前的最后一次写入
            last_write_before = None
            for write in writes:
                if write['pc_int'] <= pc_int:
                    last_write_before = write
                else:
                    break
            
            # 如果有写入，且后面还会用到（简化：假设到下次写入前都活跃）
            if last_write_before:
                # 找下一次写入
                next_write = None
                for write in writes:
                    if write['pc_int'] > pc_int:
                        next_write = write
                        break
                
                # 如果当前PC在最后写入之后、下次写入之前（或无下次写入），地址活跃
                if last_write_before['pc_int'] <= pc_int:
                    # 检查是否在下次写入之前
                    if next_write is None or pc_int < next_write['pc_int']:
                        alive_addrs.add(addr)
        
        if alive_addrs:
            pc_to_alive[pc] = alive_addrs
    
    print(f"[analyze_lifetime_pc] 分析了 {len(pc_to_alive)} 个PC的活跃集合")
    return pc_to_alive

def merge_pc_ranges(pc_to_alive: Dict[str, Set[str]]) -> List[Dict]:
    """
    合并相同活跃集合的PC范围
    
    Returns:
        [{"start": "0x9d82", "end": "0x9e00", "alive": ["0x1234", ...]}, ...]
    """
    if not pc_to_alive:
        return []
    
    # 按PC排序
    sorted_pcs = sorted(pc_to_alive.keys(), key=lambda x: int(x, 16))
    
    ranges = []
    current_range = {
        "start": sorted_pcs[0],
        "alive": sorted(list(pc_to_alive[sorted_pcs[0]]))
    }
    
    for i in range(1, len(sorted_pcs)):
        pc = sorted_pcs[i]
        prev_pc = sorted_pcs[i-1]
        
        # 如果活跃集合相同，继续当前范围
        if pc_to_alive[pc] == set(current_range["alive"]):
            continue
        
        # 否则，结束当前范围，开始新范围
        current_range["end"] = pc
        ranges.append(current_range)
        
        current_range = {
            "start": pc,
            "alive": sorted(list(pc_to_alive[pc]))
        }
    
    # 最后一个范围（结束于程序末尾）
    current_range["end"] = "0xFFFF"  # 占位符
    ranges.append(current_range)
    
    print(f"[analyze_lifetime_pc] 合并为 {len(ranges)} 个PC范围")
    return ranges

def main():
    ap = argparse.ArgumentParser(description="基于PC的生命周期分析")
    ap.add_argument("--wid-map", required=True, help="WID映射文件")
    ap.add_argument("--firmware", required=True, help="编译后的固件(.elf)")
    ap.add_argument("--out", required=True, help="输出的生命周期JSON")
    args = ap.parse_args()
    
    # 加载WID映射
    with open(args.wid_map, 'r') as f:
        wid_map = json.load(f)
    
    print(f"[analyze_lifetime_pc] 加载了 {len(wid_map.get('wid_to_info', {}))} 个WID")
    
    # 反汇编固件
    instructions = disassemble_firmware(Path(args.firmware))
    if not instructions:
        print("[analyze_lifetime_pc] 反汇编失败，退出")
        return 1
    
    # 找到关键写的真实PC
    wid_to_pc = find_critical_write_pcs(instructions, wid_map)
    
    # 分析地址生命周期
    pc_to_alive = analyze_address_lifetimes(instructions, wid_map, wid_to_pc)
    
    # 合并PC范围
    pc_ranges = merge_pc_ranges(pc_to_alive)
    
    # 输出
    output = {
        "pc_to_alive": {pc: sorted(list(addrs)) for pc, addrs in pc_to_alive.items()},
        "pc_ranges": pc_ranges,
        "statistics": {
            "total_pcs": len(pc_to_alive),
            "total_ranges": len(pc_ranges),
            "max_alive": max(len(addrs) for addrs in pc_to_alive.values()) if pc_to_alive else 0,
            "avg_alive": sum(len(addrs) for addrs in pc_to_alive.values()) / len(pc_to_alive) if pc_to_alive else 0
        }
    }
    
    with open(args.out, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"[analyze_lifetime_pc] ✅ 输出: {args.out}")
    print(f"[analyze_lifetime_pc]    - {output['statistics']['total_pcs']} 个PC")
    print(f"[analyze_lifetime_pc]    - {output['statistics']['total_ranges']} 个范围")
    print(f"[analyze_lifetime_pc]    - 最大活跃数: {output['statistics']['max_alive']}")
    print(f"[analyze_lifetime_pc]    - 平均活跃数: {output['statistics']['avg_alive']:.1f}")
    
    return 0

if __name__ == "__main__":
    exit(main())

