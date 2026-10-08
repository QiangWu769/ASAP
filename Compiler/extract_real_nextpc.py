#!/usr/bin/env python3
"""
从最终固件提取NextPC表（通过指令模式识别）

策略：搜索commit bit写入指令 (mov.b #1, &0x74xx)，
下一条指令的地址就是NextPC
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

def disassemble_elf(elf_path: Path, objdump: str = "msp430-elf-objdump") -> List[str]:
    """反汇编ELF文件"""
    try:
        result = subprocess.run(
            [objdump, "-d", str(elf_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"[extract_nextpc] ❌ 反汇编失败: {e}")
        return []
    except FileNotFoundError:
        print(f"[extract_nextpc] ❌ 找不到objdump: {objdump}")
        return []

def parse_instruction(line: str) -> Optional[Dict]:
    """解析反汇编指令行
    
    格式: "    4678:\t5c 42 0b 02 \tmov.b\t&0x020b,r12\t;comment"
    返回: {'addr': '0x4678', 'mnemonic': 'mov.b', 'operands': '&0x020b,r12', 'raw': ...}
    """
    # 简化：直接按tab分割
    if ':' not in line:
        return None
    
    # 分割地址和其余部分
    parts = line.split(':', 1)
    addr_str = parts[0].strip()
    
    # 验证地址格式
    if not re.match(r'^[0-9a-f]+$', addr_str):
        return None
    
    addr = f"0x{addr_str}"
    
    # 分割剩余部分（tab分隔）
    rest_parts = parts[1].split('\t')
    # 过滤空字符串
    rest_parts = [p.strip() for p in rest_parts if p.strip()]
    
    if len(rest_parts) < 2:
        return None
    
    bytes_str = rest_parts[0]  # 机器码
    mnemonic = rest_parts[1]  # 指令助记符
    
    # 操作数可能分散在多个tab分隔的部分，合并它们
    operands_parts = rest_parts[2:]
    operands = ' '.join(operands_parts)
    
    # 去掉注释
    if ';' in operands:
        operands = operands.split(';')[0].strip()
    
    return {
        'addr': addr,
        'addr_int': int(addr, 16),
        'mnemonic': mnemonic,
        'operands': operands,
        'raw': line.strip()
    }

def extract_nextpc_from_elf(elf_path: Path, objdump: str) -> Dict[str, str]:
    """从ELF反汇编中提取NextPC表
    
    搜索模式：mov.b #1, &0x74xx
    地址映射：0x7400=W1, 0x7402=W2, ...
    """
    print(f"[extract_nextpc] 反汇编: {elf_path}")
    lines = disassemble_elf(elf_path, objdump)
    
    if not lines:
        return {}
    
    # 解析所有指令
    instructions = []
    for line in lines:
        inst = parse_instruction(line)
        if inst:
            instructions.append(inst)
    
    print(f"[extract_nextpc] 解析了 {len(instructions)} 条指令")
    
    # 搜索commit bit写入指令: mov.b #1, &0x74xx或0x75xx
    nextpc_table = {}
    commit_pattern = re.compile(r'#1,?\s+&(0x7[45][0-9a-f]{2})', re.IGNORECASE)
    
    for i, inst in enumerate(instructions):
        # 检查是否是commit指令（必须是mov.b指令）
        if inst['mnemonic'] != 'mov.b':
            continue
        
        match = commit_pattern.search(inst['operands'])
        if not match:
            continue
        
        commit_addr_str = match.group(1)
        commit_addr = int(commit_addr_str, 16)
        
        # 计算WID号: (addr - 0x7400) / 2 + 1
        if commit_addr < 0x7400:
            continue
        
        wid_num = (commit_addr - 0x7400) // 2 + 1
        wid = f"W{wid_num}"
        
        # 下一条指令的地址 = NextPC
        if i + 1 >= len(instructions):
            print(f"[extract_nextpc] 警告: {wid} @ {inst['addr']} 后面没有下一条指令")
            continue
        
        nextpc_inst = instructions[i + 1]
        nextpc_addr = nextpc_inst['addr']
        
        nextpc_table[wid] = nextpc_addr
    
    print(f"[extract_nextpc] 提取了 {len(nextpc_table)} 个NextPC")
    
    return nextpc_table

def validate_nextpc_with_wid_map(nextpc_table: Dict[str, str], wid_map: Dict) -> bool:
    """验证NextPC表与WID映射是否一致"""
    wid_to_info = wid_map.get("wid_to_info", {})
    
    # 检查所有WID是否都有NextPC
    missing_wids = []
    for wid in wid_to_info.keys():
        if wid not in nextpc_table:
            missing_wids.append(wid)
    
    if missing_wids:
        print(f"[extract_nextpc] ⚠️ 警告: {len(missing_wids)} 个WID缺少NextPC:")
        for wid in missing_wids[:10]:
            print(f"  - {wid}")
        if len(missing_wids) > 10:
            print(f"  ... 还有 {len(missing_wids) - 10} 个")
        return False
    
    # 检查是否有多余的NextPC
    extra_wids = set(nextpc_table.keys()) - set(wid_to_info.keys())
    if extra_wids:
        print(f"[extract_nextpc] ⚠️ 警告: {len(extra_wids)} 个NextPC没有对应的WID")
    
    return len(missing_wids) == 0

def main():
    ap = argparse.ArgumentParser(description="从最终固件提取NextPC表")
    ap.add_argument("--elf", required=True, help="最终固件ELF文件")
    ap.add_argument("--wid-map", required=True, help="WID映射文件（用于验证）")
    ap.add_argument("--out", default="build/nextpc_table.json", help="输出NextPC表")
    ap.add_argument("--objdump", default="msp430-elf-objdump", help="objdump工具路径")
    args = ap.parse_args()
    
    elf_path = Path(args.elf)
    wid_map_path = Path(args.wid_map)
    
    if not elf_path.exists():
        print(f"[extract_nextpc] ❌ ELF文件不存在: {elf_path}")
        return 1
    
    if not wid_map_path.exists():
        print(f"[extract_nextpc] ❌ WID映射文件不存在: {wid_map_path}")
        return 1
    
    # 加载WID映射
    with open(wid_map_path, 'r') as f:
        wid_map = json.load(f)
    
    total_wids = len(wid_map.get("wid_to_info", {}))
    print(f"[extract_nextpc] WID总数: {total_wids}")
    
    # 提取NextPC
    nextpc_table = extract_nextpc_from_elf(elf_path, args.objdump)
    
    # 验证
    is_valid = validate_nextpc_with_wid_map(nextpc_table, wid_map)
    
    # 保存
    output = {
        "nextpc_table": nextpc_table,
        "statistics": {
            "total_wids": total_wids,
            "total_nextpc": len(nextpc_table),
            "coverage": f"{len(nextpc_table) / max(total_wids, 1) * 100:.1f}%"
        }
    }
    
    output_path = Path(args.out)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"[extract_nextpc] ✅ NextPC表已保存: {output_path}")
    print(f"[extract_nextpc] 覆盖率: {output['statistics']['coverage']}")
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    exit(main())
