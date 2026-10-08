#!/usr/bin/env python3
"""
Stage11包装器：在标准恢复逻辑基础上添加位图支持
完全不修改stage11_generate_restore_dedup.py，只在其输出上追加位图代码
"""

import json
import subprocess
import sys
import re
from pathlib import Path


def inject_bitmap_to_restore_table(restore_asm_file, fram_slots, output_file):
    """
    在现有恢复逻辑中添加位图支持
    
    步骤：
    1. 在恢复表中为位图WID添加0xFFFB标记的表项
    2. 在恢复代码中添加_restore_bitmap分支
    3. 完全不修改现有的恢复表项和恢复代码
    """
    
    # 检查是否有位图WID
    bitmap_wids = {}
    for wid, slot_info in fram_slots['wid_to_slot'].items():
        if slot_info.get('_use_bitmap', False):
            bitmap_wids[wid] = slot_info
    
    if not bitmap_wids:
        print("  无位图WID，使用标准恢复逻辑")
        import shutil
        shutil.copy(restore_asm_file, output_file)
        return
    
    print(f"  位图恢复：处理 {len(bitmap_wids)} 个数组WID")
    
    # 读取标准恢复汇编
    with open(restore_asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    
    # 按数组分组（同一数组的多个WID共享一个位图结构）
    array_groups = {}
    for wid, slot_info in bitmap_wids.items():
        group = slot_info.get('_array_group', slot_info['logical_addr'])
        if group not in array_groups:
            array_groups[group] = []
        array_groups[group].append(wid)
    
    # ===== 第一步：在恢复表中为位图WID添加特殊表项 =====
    table_inserted = False
    bitmap_branch_inserted = False
    
    for i, line in enumerate(lines):
        output_lines.append(line)
        
        # 在恢复表定义后、恢复代码前插入位图表项
        if not table_inserted and '_restore_table:' in line:
            # 找到恢复表结束位置（在恢复代码.section .text之前）
            # 先继续输出，找到.section .text时插入
            continue
        
        if not table_inserted and '.section .text' in line:
            # 在这里插入位图恢复表项
            output_lines.pop()  # 移除刚加的.section .text
            
            output_lines.append('\n; ===== 位图数组恢复表（新增） =====\n')
            
            for group, wid_list in array_groups.items():
                # 每个数组组一个位图表项
                first_wid = wid_list[0]
                bs = bitmap_wids[first_wid]['_bitmap_struct']
                
                output_lines.append(f'; 位图数组: {group}\n')
                output_lines.append(f'; WID: {", ".join(wid_list)}\n')
                output_lines.append(f'_bitmap_struct_{group.replace("::", "_").replace("+", "_")}:\n')
                output_lines.append(f'    .word 0xFFFB                   ; 标记：位图结构\n')
                output_lines.append(f'    .word {bs["base_addr_slot"]}   ; 基址槽位\n')
                output_lines.append(f'    .word {bs["bitmap_slot"]}      ; 位图槽位\n')
                output_lines.append(f'    .word {bs["values_base"]}      ; values基址\n')
                output_lines.append(f'    .word {bs["max_elements"]}     ; 最大元素数\n')
                output_lines.append(f'    .word {bs["elem_size"]}        ; 元素大小\n')
                output_lines.append('\n')
            
            output_lines.append(line)  # 重新加上.section .text
            table_inserted = True
            continue
        
        # 在_restore_items的分支判断中添加位图分支
        if not bitmap_branch_inserted and '_restore_indirect' in line and 'JEQ' in line:
            # 在这一行后添加位图分支判断
            output_lines.append('    CMP.W   #0xFFFB, R15\n')
            output_lines.append('    JEQ     _restore_bitmap        ; 位图数组恢复（新增）\n')
            bitmap_branch_inserted = True
    
    # ===== 第二步：在文件末尾追加位图恢复代码 =====
    if bitmap_branch_inserted:
        output_lines.append('\n; ===== 位图恢复代码（新增分支） =====\n')
        output_lines.append(generate_bitmap_restore_asm())
    
    # 写入输出
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    print(f"  ✓ 位图恢复代码已集成")


def generate_bitmap_restore_asm():
    """生成位图恢复汇编代码"""
    return """
_restore_bitmap:
    ; 【位图数组恢复】
    ; 格式: [0xFFFB, base_slot, bitmap_slot, values_base, max_count, elem_size]
    
    ; === 步骤1: 读取参数 ===
    MOV.W   @R14+, R10             ; R10 = base_addr_slot指针
    MOV.W   @R10, R10              ; R10 = 数组基址（栈地址）
    
    MOV.W   @R14+, R11             ; R11 = bitmap_slot指针
    MOV.W   @R11, R11              ; R11 = 位图值
    
    MOV.W   @R14+, R12             ; R12 = values_base
    MOV.W   @R14+, R13             ; R13 = max_count
    MOV.W   @R14+, R8              ; R8 = elem_size
    
    ; 基址边界检查
    CMP.W   #0x2400, R10
    JHS     _restore_items         ; 超出栈范围
    CMP.W   #0x1C00, R10
    JLO     _restore_items
    
    ; === 步骤2: 扫描位图，恢复脏元素 ===
    PUSH    R8                     ; 保存elem_size
    MOV.W   #0, R15                ; R15 = index
    
__bitmap_scan_loop:
    ; 检查是否完成
    CMP.W   R13, R15               ; index < max_count?
    JGE     __bitmap_scan_done
    
    ; 检查bit[index]
    MOV.W   R11, R9                ; R9 = bitmap副本
    MOV.W   R15, R8                ; R8 = shift_count
    
    ; 右移index次
    CMP.W   #0, R8
    JEQ     __bitmap_check_bit
__bitmap_shift_right:
    RRA.W   R9                     ; bitmap >>= 1
    SUB.W   #1, R8
    JNZ     __bitmap_shift_right
    
__bitmap_check_bit:
    BIT.W   #1, R9                 ; 测试最低位
    JZ      __bitmap_next_elem     ; bit=0，跳过
    
    ; === 步骤3: 恢复该元素 ===
    ; 读取values[index]
    MOV.W   R15, R9                ; R9 = index
    RLA.W   R9                     ; R9 *= 2 (字偏移)
    ADD.W   R12, R9                ; R9 = &values[index]
    MOV.W   @R9, R9                ; R9 = values[index]
    
    ; 计算目标地址 = base + index * elem_size
    POP     R8                     ; 恢复elem_size
    PUSH    R8
    MOV.W   R15, R14               ; R14 = index
    
    ; 根据元素大小计算偏移
    CMP.W   #1, R8
    JEQ     __bitmap_no_mult
    CMP.W   #2, R8
    JEQ     __bitmap_mult_2
    ; elem_size = 4
    RLA.W   R14
    RLA.W   R14
    JMP     __bitmap_no_mult
__bitmap_mult_2:
    RLA.W   R14
__bitmap_no_mult:
    
    ADD.W   R10, R14               ; R14 = base + offset
    
    ; 目标地址安全检查
    CMP.W   #0x2400, R14
    JHS     __bitmap_next_elem
    CMP.W   #0x1C00, R14
    JLO     __bitmap_next_elem
    
    ; 写回
    MOV.W   R9, 0(R14)             ; array[index] = value
    
__bitmap_next_elem:
    ADD.W   #1, R15                ; index++
    JMP     __bitmap_scan_loop

__bitmap_scan_done:
    POP     R8                     ; 恢复栈平衡
    JMP     _restore_items         ; 继续处理下一个恢复项

"""


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Stage11位图包装器')
    parser.add_argument('--pc-ranges', required=True)
    parser.add_argument('--wid-pc-map', required=True)
    parser.add_argument('--fram-slots', required=True)
    parser.add_argument('--function-info', required=True)
    parser.add_argument('--wid-backup-regs', default='build/wid_backup_regs.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--format', default='asm')
    
    args = parser.parse_args()
    
    print("\n[Stage11位图] 生成恢复逻辑（标准+位图）")
    
    # 步骤1: 先运行标准stage11
    print("  步骤1: 运行标准stage11...")
    temp_output = args.output + '.standard'
    
    cmd = [
        'python3', 'Compiler/stage11_generate_restore_dedup.py',
        '--pc-ranges', args.pc_ranges,
        '--wid-pc-map', args.wid_pc_map,
        '--fram-slots', args.fram_slots,
        '--function-info', args.function_info,
        '--wid-backup-regs', args.wid_backup_regs,
        '--output', temp_output,
        '--format', args.format
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    
    # 步骤2: 加载数据
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 步骤3: 在标准输出上追加位图恢复
    print("  步骤2: 添加位图恢复代码...")
    inject_bitmap_to_restore_table(
        temp_output,
        fram_slots,
        args.output
    )
    
    print(f"  ✓ 位图模式恢复逻辑生成完成: {args.output}")
    
    # 清理临时文件
    Path(temp_output).unlink()
    
    return 0


if __name__ == '__main__':
    exit(main())















