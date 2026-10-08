#!/usr/bin/env python3
"""
Stage11 位图恢复代码生成模块
为使用位图的数组WID生成恢复逻辑
完全不修改现有恢复逻辑，只添加新的恢复分支
"""

def generate_bitmap_restore_entries(restore_list, fram_slots_data):
    """
    生成位图恢复表项（追加到现有表项后）
    
    格式：[0xFFFB, base_addr_slot, bitmap_slot, values_base, max_elements, elem_size]
    """
    
    entries = []
    
    for item in restore_list:
        # 检查是否使用位图
        if not item.get('_use_bitmap', False):
            continue  # 不是位图WID，跳过
        
        bs = item['_bitmap_struct']
        
        entry = []
        entry.append(f"    .word 0xFFFB                   ; 标记：位图数组恢复\n")
        entry.append(f"    .word {bs['base_addr_slot']}   ; 数组基址槽位\n")
        entry.append(f"    .word {bs['bitmap_slot']}      ; 位图槽位\n")
        entry.append(f"    .word {bs['values_base']}      ; values数组基址\n")
        entry.append(f"    .word {bs['max_elements']}     ; 最大元素数\n")
        entry.append(f"    .word {bs['elem_size']}        ; 元素大小\n")
        
        entries.append(''.join(entry))
    
    return entries


def generate_bitmap_restore_code():
    """
    生成位图恢复的汇编代码（追加到现有恢复代码后）
    
    处理流程：
    1. 读取位图结构参数
    2. 扫描位图，找出所有脏位
    3. 对每个脏位，从values[index]恢复到 base+index*elem_size
    """
    
    code = """
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
    
    return code


def append_bitmap_restore_to_asm(restore_asm_file):
    """
    将位图恢复代码追加到现有的恢复汇编文件
    不修改现有代码，只在最后追加
    """
    
    with open(restore_asm_file, 'r') as f:
        lines = f.readlines()
    
    # 找到 _restore_items 分支处理的位置
    # 在那里添加位图分支判断
    output_lines = []
    inserted = False
    
    for i, line in enumerate(lines):
        output_lines.append(line)
        
        # 在第一个恢复分支判断后插入位图分支判断
        if not inserted and '_restore_indirect' in line and 'JEQ' in line:
            # 在现有分支后添加位图分支判断
            output_lines.append('    CMP.W   #0xFFFB, R15\n')
            output_lines.append('    JEQ     _restore_bitmap        ; 位图数组恢复\n')
            inserted = True
    
    # 在文件末尾追加位图恢复代码
    if inserted:
        output_lines.append('\n; ===== 位图恢复分支（新增） =====\n')
        output_lines.append(generate_bitmap_restore_code())
    
    with open(restore_asm_file, 'w') as f:
        f.writelines(output_lines)
    
    print(f"  ✓ 位图恢复代码已追加到: {restore_asm_file}")


def main():
    """
    独立工具：将位图恢复功能添加到现有恢复逻辑
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Stage11位图恢复扩展')
    parser.add_argument('restore_asm', help='现有的恢复汇编文件')
    parser.add_argument('--output', help='输出文件（可选，默认覆盖输入）')
    
    args = parser.parse_args()
    
    output_file = args.output if args.output else args.restore_asm
    
    # 追加位图恢复代码
    append_bitmap_restore_to_asm(args.restore_asm)
    
    if output_file != args.restore_asm:
        import shutil
        shutil.copy(args.restore_asm, output_file)
        print(f"  ✓ 输出到: {output_file}")
    
    return 0


if __name__ == '__main__':
    exit(main())















