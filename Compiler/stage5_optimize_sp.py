#!/usr/bin/env python3
"""
Stage 5b: SP备份优化
删除不必要的 MOV.W R1, &ASAP_SP_SAVE 指令

原理：只有在"上一个检查点之后到当前检查点之间有修改SP的指令"时才需要备份SP
- 函数入口(prologue)后的第一个检查点：必须备份SP（因为SUB.W #x, R1）
- PUSH/POP 指令后：必须备份SP
- 目标是SP的指令后：必须备份SP
- 其他普通MOV写操作后：可以跳过SP备份

输入: build/A_instrumented.s (stage5输出)
输出: build/A_instrumented_opt.s
"""
import argparse
import re
import sys

def instruction_modifies_sp(line):
    """判断指令是否修改了SP (R1)"""
    if not line:
        return False
    
    line_stripped = line.strip()
    line_upper = line_stripped.upper()
    
    # 跳过空行、注释、标签、伪指令
    if not line_upper:
        return False
    if line_upper.startswith(';'):
        return False
    if line_stripped.endswith(':'):
        return False
    if line_upper.startswith('.'):
        return False
    
    # 1. PUSH 指令（SP -= 2）
    if re.match(r'^PUSH(\.W|\.B)?\s+', line_upper):
        return True
    
    # 2. POP 指令（SP += 2）
    if re.match(r'^POP(\.W|\.B)?\s+', line_upper):
        return True
    
    # 3. PUSHM / POPM（多寄存器）
    if line_upper.startswith('PUSHM') or line_upper.startswith('POPM'):
        return True
    
    # 4. 目标操作数是 SP/R1 的指令
    # 匹配: MOV xxx, SP / MOV xxx, R1 / ADD #imm, SP / SUB #imm, R1 等
    # 注意要排除 MOV.W R1, &xxx 这样的读取SP的指令
    dst_is_sp = re.search(r',\s*(SP|R1)\s*(;.*)?$', line_upper)
    if dst_is_sp:
        return True
    
    # 5. 使用 @SP+ 或 @R1+ 寻址模式（隐式 SP += 2）
    if '@SP+' in line_upper or '@R1+' in line_upper:
        return True
    
    # 6. 使用 -(SP) 或 -(R1) 寻址模式（隐式 SP -= 2）
    # 注意：MSP430 实际不支持这个，但为完整性保留
    if '-(SP)' in line_upper or '-(R1)' in line_upper:
        return True
    
    return False

def is_sp_backup_instruction(line):
    """判断是否是 SP 备份指令"""
    line_upper = line.upper()
    return 'MOV.W R1, &ASAP_SP_SAVE' in line_upper or \
           'MOV.W SP, &ASAP_SP_SAVE' in line_upper

def is_wid_save_instruction(line):
    """判断是否是 WID 保存指令"""
    return '&ASAP_WID_SAVE' in line.upper() and 'MOV.W #' in line.upper()

def is_prologue_end(line):
    """判断是否是函数prologue结束标记"""
    return '; end of prologue' in line.lower()

def is_function_start(line):
    """判断是否是函数开始（函数标签）"""
    stripped = line.strip()
    # 函数标签：以字母或下划线开头，以冒号结尾，且不是局部标签(.L开头)
    if stripped.endswith(':') and not stripped.startswith('.'):
        label = stripped[:-1]
        if re.match(r'^[a-zA-Z_][\w]*$', label):
            return True
    return False

def optimize_sp_backup(input_file, output_file, verbose=False):
    """优化SP备份：删除不必要的备份指令"""
    
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    removed_count = 0
    kept_count = 0
    
    # 跟踪自上一个检查点以来SP是否被修改
    # 初始为True，因为程序开始时SP状态未知
    sp_modified_since_last_checkpoint = True
    
    # 当前函数名（用于调试输出）
    current_function = None
    
    # 是否在函数prologue中
    in_prologue = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # 检测函数开始
        if is_function_start(line):
            current_function = line_stripped[:-1]  # 去掉冒号
            in_prologue = True
            sp_modified_since_last_checkpoint = True  # 新函数，SP状态重置
            output_lines.append(line)
            continue
        
        # 检测prologue结束
        if is_prologue_end(line):
            in_prologue = False
            # prologue 通常会修改SP（SUB.W #x, R1），所以标记为已修改
            sp_modified_since_last_checkpoint = True
            output_lines.append(line)
            continue
        
        # 检测 SP 备份指令
        if is_sp_backup_instruction(line):
            if sp_modified_since_last_checkpoint:
                # 需要保留
                output_lines.append(line)
                kept_count += 1
                if verbose:
                    print(f"  [保留] 行{i+1}: SP备份 (SP已被修改)")
            else:
                # 可以删除
                removed_count += 1
                if verbose:
                    print(f"  [删除] 行{i+1}: SP备份 (SP未变化)")
                # 不添加到输出
            continue
        
        # 检测 WID 保存指令（检查点结束标记）
        if is_wid_save_instruction(line):
            # 检查点完成，重置SP修改标志
            sp_modified_since_last_checkpoint = False
            output_lines.append(line)
            continue
        
        # 其他指令：检查是否修改SP
        if instruction_modifies_sp(line):
            sp_modified_since_last_checkpoint = True
            if verbose:
                print(f"  [检测] 行{i+1}: 修改SP的指令: {line_stripped}")
        
        output_lines.append(line)
    
    # 写入输出
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    return removed_count, kept_count

def main():
    parser = argparse.ArgumentParser(description='Stage 5b: SP备份优化')
    parser.add_argument('input_file', help='输入汇编文件')
    parser.add_argument('--output', '-o', default=None, help='输出汇编文件（默认覆盖输入）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    parser.add_argument('--dry-run', '-n', action='store_true', help='只分析不修改')
    
    args = parser.parse_args()
    
    # 默认输出文件
    if args.output is None:
        if args.dry_run:
            args.output = '/dev/null'
        else:
            args.output = args.input_file  # 覆盖原文件
    
    print(f"Stage 5b: SP备份优化")
    print(f"  输入: {args.input_file}")
    
    removed, kept = optimize_sp_backup(args.input_file, args.output, args.verbose)
    
    total = removed + kept
    if total > 0:
        reduction = removed / total * 100
    else:
        reduction = 0
    
    print(f"  ✓ SP备份优化完成:")
    print(f"    - 删除冗余SP备份: {removed} 条")
    print(f"    - 保留必要SP备份: {kept} 条")
    print(f"    - 优化率: {reduction:.1f}%")
    
    if not args.dry_run:
        print(f"  ✓ 输出: {args.output}")
    else:
        print(f"  (dry-run模式，未修改文件)")
    
    # 返回统计信息
    return {
        'removed': removed,
        'kept': kept,
        'total': total,
        'reduction_percent': reduction
    }

if __name__ == '__main__':
    main()

