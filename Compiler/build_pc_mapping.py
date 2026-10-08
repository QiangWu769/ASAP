#!/usr/bin/env python3
"""
构建PC映射：从归一化汇编(无PC)到实际地址(有PC)的映射

用途:
  - 读取 A_normalized.s 和 A_normalized_real.s
  - 通过指令匹配建立行号/指令到实际PC的映射
  - 供 assign_wid 使用，将相对PC转换为实际PC
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

def extract_instructions_from_sym_asm(asm_file: Path) -> List[Tuple[str, str]]:
    """
    从符号汇编(A_normalized.s)中提取指令序列
    
    Returns:
        [(pc_or_line, instruction), ...]
    """
    instructions = []
    with open(asm_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            # 跳过空行、注释、指令
            if not stripped or stripped.startswith(';') or stripped.startswith('.') or stripped.startswith('#'):
                continue
            if stripped.endswith(':'):  # 标签
                continue
            
            # 这是一条指令
            # 尝试匹配PC（可能有也可能没有）
            m = re.match(r'^([0-9a-f]+):\s+(.+)', stripped)
            if m:
                pc = m.group(1)
                inst = m.group(2)
                instructions.append((f"0x{pc}", inst))
            else:
                # 没有PC，使用行号
                instructions.append((f"line_{line_num}", stripped))
    
    return instructions

def extract_instructions_from_real_asm(asm_file: Path) -> List[Tuple[str, str]]:
    """
    从实际汇编(A_normalized_real.s)中提取指令序列
    
    Returns:
        [(actual_pc, instruction), ...]
    """
    instructions = []
    with open(asm_file, 'r') as f:
        for line in f:
            # 匹配格式: "    4678:	43 92 00 20 	MOV.W	#1,	&WDTCTL	;r3 As==01"
            m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f ]+)\s+(.+)', line)
            if m:
                pc = m.group(1)
                inst = m.group(3).strip()
                instructions.append((f"0x{pc}", inst))
    
    return instructions

def normalize_instruction(inst: str) -> str:
    """归一化指令，用于匹配（去掉注释、多余空格等）"""
    # 去掉注释
    if ';' in inst:
        inst = inst.split(';')[0]
    # 统一空白
    inst = re.sub(r'\s+', ' ', inst).strip()
    # 转大写
    inst = inst.upper()
    return inst

def build_pc_mapping(sym_asm: Path, real_asm: Path) -> Dict[str, str]:
    """
    构建PC映射：sym_asm的PC/line → real_asm的实际PC
    
    Args:
        sym_asm: A_normalized.s (符号汇编)
        real_asm: A_normalized_real.s (实际汇编)
    
    Returns:
        {sym_pc: real_pc, ...}
    """
    sym_insts = extract_instructions_from_sym_asm(sym_asm)
    real_insts = extract_instructions_from_real_asm(real_asm)
    
    print(f"[build_pc_mapping] 符号汇编指令数: {len(sym_insts)}")
    print(f"[build_pc_mapping] 实际汇编指令数: {len(real_insts)}")
    
    # 归一化指令
    sym_norm = [(pc, normalize_instruction(inst)) for pc, inst in sym_insts]
    real_norm = [(pc, normalize_instruction(inst)) for pc, inst in real_insts]
    
    # 创建映射（简单方法：按顺序匹配）
    pc_map = {}
    real_idx = 0
    
    for sym_pc, sym_inst in sym_norm:
        # 从当前位置开始找匹配的指令
        found = False
        for i in range(real_idx, min(real_idx + 10, len(real_norm))):  # 向前看10条
            real_pc, real_inst = real_norm[i]
            if sym_inst == real_inst:
                pc_map[sym_pc] = real_pc
                real_idx = i + 1
                found = True
                break
        
        if not found and sym_pc.startswith('0x'):
            # 如果符号汇编本身就有PC，可能直接对应
            # （这通常不会发生，但作为fallback）
            pass
    
    print(f"[build_pc_mapping] 成功映射 {len(pc_map)} 条指令")
    
    return pc_map

def main():
    parser = argparse.ArgumentParser(
        description='构建PC映射：符号汇编PC → 实际PC'
    )
    parser.add_argument(
        '--sym-asm',
        type=Path,
        required=True,
        help='符号汇编文件 (A_normalized.s)'
    )
    parser.add_argument(
        '--real-asm',
        type=Path,
        required=True,
        help='实际汇编文件 (A_normalized_real.s)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='输出JSON文件 (pc_mapping.json)'
    )
    
    args = parser.parse_args()
    
    if not args.sym_asm.exists():
        print(f"错误: {args.sym_asm} 不存在")
        return 1
    
    if not args.real_asm.exists():
        print(f"错误: {args.real_asm} 不存在")
        return 1
    
    pc_map = build_pc_mapping(args.sym_asm, args.real_asm)
    
    metadata = {
        'description': '符号汇编PC到实际PC的映射',
        'sym_asm': str(args.sym_asm),
        'real_asm': str(args.real_asm),
        'pc_mapping': pc_map
    }
    
    with open(args.output, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"[build_pc_mapping] PC映射已保存到 {args.output}")
    
    return 0

if __name__ == '__main__':
    exit(main())

