#!/usr/bin/env python3
"""
生成NextPC[WID]表 - 插桩后重建CFG/反汇编

对插桩后的程序重建CFG/反汇编，将第二条MOV的顺序后继地址作为NextPC[WID]。
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

def find_commit_instructions(instructions: List[Dict]) -> List[Dict]:
    """找到所有commit指令（第二条MOV）"""
    commit_instructions = []
    
    for i, instr in enumerate(instructions):
        instruction = instr['instruction']
        
        # 查找commit指令模式：MOV #1, &__RS_COMMIT_W*
        if 'MOV #1, &__RS_COMMIT_' in instruction and '__RS_COMMIT_W' in instruction:
            commit_instructions.append({
                'line': instr['line'],
                'pc': instr['pc'],
                'instruction': instruction,
                'index': i
            })
    
    return commit_instructions

def extract_wid_from_commit(instruction: str) -> str:
    """从commit指令中提取WID"""
    # 匹配模式：MOV #1, &__RS_COMMIT_W*
    match = re.search(r'__RS_COMMIT_(W\d+)', instruction)
    if match:
        return match.group(1)
    return ""

def find_next_instruction(instructions: List[Dict], commit_index: int) -> Dict:
    """找到commit指令的下一条指令"""
    if commit_index + 1 < len(instructions):
        return instructions[commit_index + 1]
    return None

def generate_nextpc_table(instructions: List[Dict]) -> Dict:
    """生成NextPC[WID]表"""
    print("[NextPC生成] 开始生成NextPC[WID]表...")
    
    # 找到所有commit指令
    commit_instructions = find_commit_instructions(instructions)
    print(f"[NextPC生成] 找到 {len(commit_instructions)} 个commit指令")
    
    nextpc_table = {}
    
    for commit_instr in commit_instructions:
        # 提取WID
        wid = extract_wid_from_commit(commit_instr['instruction'])
        if not wid:
            continue
            
        # 找到下一条指令
        next_instr = find_next_instruction(instructions, commit_instr['index'])
        if next_instr:
            nextpc_table[wid] = {
                'next_pc': next_instr['pc'],
                'next_line': next_instr['line'],
                'next_instruction': next_instr['instruction'],
                'commit_line': commit_instr['line'],
                'commit_instruction': commit_instr['instruction']
            }
            print(f"[NextPC生成] {wid}: NextPC = {next_instr['pc']} (行{next_instr['line']})")
        else:
            # 如果是最后一条指令，使用程序结束标记
            nextpc_table[wid] = {
                'next_pc': 'PROGRAM_END',
                'next_line': -1,
                'next_instruction': 'PROGRAM_END',
                'commit_line': commit_instr['line'],
                'commit_instruction': commit_instr['instruction']
            }
            print(f"[NextPC生成] {wid}: NextPC = PROGRAM_END (程序结束)")
    
    return nextpc_table

def main():
    parser = argparse.ArgumentParser(description='生成NextPC[WID]表')
    parser.add_argument('--asm', required=True, help='插桩后的汇编文件')
    parser.add_argument('--out', required=True, help='输出文件')
    
    args = parser.parse_args()
    
    # 解析汇编文件
    print(f"[NextPC生成] 解析汇编文件: {args.asm}")
    instructions = parse_asm_file(args.asm)
    print(f"[NextPC生成] 解析了 {len(instructions)} 条指令")
    
    # 生成NextPC表
    nextpc_table = generate_nextpc_table(instructions)
    
    # 生成报告
    report = {
        'nextpc_table': nextpc_table,
        'summary': {
            'total_wids': len(nextpc_table),
            'total_instructions': len(instructions)
        }
    }
    
    # 保存结果
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"[NextPC生成] NextPC表生成完成")
    print(f"[NextPC生成] 生成了 {len(nextpc_table)} 个NextPC条目")
    print(f"[NextPC生成] 结果保存到: {args.out}")

if __name__ == '__main__':
    main()