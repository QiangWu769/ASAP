#!/usr/bin/env python3
"""
应用归一化到符号化汇编文件

将归一化后的指令应用到源汇编文件中，生成归一化后的符号化汇编文件。
"""

import json
import argparse
from pathlib import Path
import re

def load_normalized_data(normalized_json_path: str):
    """加载归一化数据"""
    with open(normalized_json_path, 'r') as f:
        return json.load(f)

def load_sym_asm(sym_asm_path: str):
    """加载符号化汇编文件"""
    with open(sym_asm_path, 'r') as f:
        return f.readlines()

def apply_normalization(sym_asm_lines, normalized_data):
    """应用归一化到汇编文件"""
    
    # 创建指令模式到归一化指令的映射
    # 归一化后的指令格式：MOV.B R12, &PASEL0_H
    inst_to_normalized = {}
    for entry in normalized_data:
        if entry.get('normalized_from'):
            # 提取原始指令（归一化前）
            mnemonic = entry['mnemonic'].upper()
            original_ops = entry['original_operands']
            # 标准化格式：MOV.B R12, &PASEL0_H
            inst_key = f"{mnemonic}\t{original_ops}".replace(' ', '').upper()
            inst_to_normalized[inst_key] = entry
    
    # 创建归一化指令的插入和替换列表
    insertions = []  # (line_num, instruction_to_insert)
    replacements = []  # (line_num, new_line)
    
    # 处理每一行
    for line_num, line in enumerate(sym_asm_lines):
        # 查找指令行（以\t开头，包含逗号）
        inst_match = re.match(r'^\s+([A-Z]+(?:\.[BW])?)\s+(.+)', line)
        if inst_match:
            mnemonic = inst_match.group(1).upper()
            operands = inst_match.group(2).strip()
            
            # 移除注释
            if '{' in operands:
                operands = operands.split('{')[0].strip()
            
            # 标准化格式
            inst_key = f"{mnemonic}\t{operands}".replace(' ', '').upper()
            
            # 检查是否匹配
            if inst_key in inst_to_normalized:
                normalized_entry = inst_to_normalized[inst_key]
                reg = normalized_entry['normalized_from']
                slot_addr = normalized_entry['shadow_slot']
                width = '.W' if normalized_entry.get('width', 2) == 2 else '.B'
                
                # 在关键写指令之前插入shadow slot写入指令
                shadow_instruction = f"\tMOV{width}\t{reg.upper()}, &{slot_addr}     ; normalize {reg}\n"
                insertions.append((line_num, shadow_instruction))
                
                # 修改原指令：替换源操作数（从 R12 改为 &0x235e）
                # 提取目标操作数（逗号后的部分）
                if ',' in operands:
                    _, dst = operands.rsplit(',', 1)
                    dst = dst.strip()
                    # 生成新指令：源从shadow slot读取
                    new_operands = f"&{slot_addr}, {dst}"
                    # 保留原始行的缩进和注释，确保换行符
                    indent = line[:len(line) - len(line.lstrip())]
                    comment = ''
                    if '{' in line:
                        comment = ' ' + line.split('{', 1)[1].rstrip('\n')
                    new_line = f"{indent}{mnemonic}\t{new_operands}{comment}\n"
                    replacements.append((line_num, new_line))
    
    # 先应用替换（修改原指令）
    for line_num, new_line in replacements:
        sym_asm_lines[line_num] = new_line
    
    # 再应用插入（从后往前插入，避免行号变化）
    for line_num, instruction in reversed(insertions):
        sym_asm_lines.insert(line_num, instruction)
    
    return sym_asm_lines

def main():
    parser = argparse.ArgumentParser(description="应用归一化到符号化汇编文件")
    parser.add_argument("--sym-asm", required=True, help="源符号化汇编文件")
    parser.add_argument("--normalized", required=True, help="归一化数据JSON文件")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    
    args = parser.parse_args()
    
    print(f"[apply_normalization] 加载归一化数据: {args.normalized}")
    normalized_data = load_normalized_data(args.normalized)
    
    print(f"[apply_normalization] 加载符号化汇编: {args.sym_asm}")
    sym_asm_lines = load_sym_asm(args.sym_asm)
    
    print(f"[apply_normalization] 应用归一化...")
    normalized_lines = apply_normalization(sym_asm_lines, normalized_data)
    
    # 输出归一化后的汇编文件
    output_path = Path(args.out_dir) / "A_normalized.s"
    with open(output_path, 'w') as f:
        f.writelines(normalized_lines)
    
    added_count = len(normalized_lines) - len(sym_asm_lines)
    print(f"[apply_normalization] 归一化完成")
    print(f"[apply_normalization] 输出文件: {output_path}")
    print(f"[apply_normalization] 插入了 {added_count} 条shadow slot写入指令")
    print(f"[apply_normalization] {len(sym_asm_lines)}行 → {len(normalized_lines)}行")

if __name__ == "__main__":
    main()

