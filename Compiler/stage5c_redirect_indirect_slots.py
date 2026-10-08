#!/usr/bin/env python3
"""
Stage 5c: 重定向间接地址的备份槽位
在stage5之后运行，根据调用图将间接地址的备份重定向到调用者栈变量的槽位

例如：
  record_stats::R12+0 实际是 recognize::SP+16
  将 MOV.W @R12, &__SLOT_record_stats_R12_0
  改为 MOV.W @R12, &__SLOT_recognize_SP_16
"""
import argparse
import json
import re

def find_caller_stack_slot(func_name, reg_offset, call_graph, fram_slots):
    """找到间接地址对应的调用者栈变量的槽位
    
    Args:
        func_name: 当前函数（如 record_stats）
        reg_offset: 寄存器偏移（如 "R12+0"）
        call_graph: 调用图
        fram_slots: FRAM槽位映射
    
    Returns:
        调用者栈变量的槽位符号，如果找不到则返回None
    """
    # 获取调用者列表
    callers = call_graph.get('call_graph', {}).get(func_name, {}).get('callers', [])
    if not callers:
        return None
    
    # 简化：假设只有一个调用者（大多数情况）
    caller = callers[0]
    
    # 解析寄存器偏移
    if '+' in reg_offset:
        reg_name, offset_str = reg_offset.split('+')
        offset = int(offset_str)
    else:
        reg_name = reg_offset
        offset = 0
    
    # 在调用者的栈变量中查找可能的对应关系
    # 启发式：假设第一个参数（R12）指向调用者栈上的一个结构体
    # 需要找到对应偏移的成员
    
    addr_to_slot = fram_slots.get('addr_to_slot', {})
    
    # 查找调用者的栈变量，看哪个可能对应这个间接地址
    # 例如：record_stats的R12是stats指针，指向recognize的SP+16（stats.totalCount）
    # R12+0 对应 SP+16
    # R12+2 对应 SP+18
    # R12+4 对应 SP+20
    
    # 策略：遍历调用者的栈变量，找到连续的变量（可能是结构体成员）
    caller_vars = {}
    for logical_addr, slot_info in addr_to_slot.items():
        if logical_addr.startswith(f'{caller}::SP+'):
            parts = logical_addr.split('::SP+')
            if len(parts) == 2:
                sp_offset = int(parts[1])
                caller_vars[sp_offset] = slot_info
    
    # 如果调用者有栈变量，尝试匹配
    # 简单启发式：找到第一个栈变量的基址，加上reg_offset
    if caller_vars:
        # 找到最小的SP偏移（可能是结构体的起始）
        base_offsets = sorted(caller_vars.keys())
        
        # 尝试匹配：假设第一个连续的栈变量组是目标结构体
        # 例如：SP+16, SP+18, SP+20 是stats的三个成员
        for base_offset in base_offsets:
            target_offset = base_offset + offset
            if target_offset in caller_vars:
                return caller_vars[target_offset]['slot_symbol']
    
    return None

def redirect_indirect_slots(asm_file, call_graph, fram_slots, output_file):
    """重定向间接地址的备份槽位"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    redirected_count = 0
    current_func = None
    
    for i, line in enumerate(lines):
        # 检测函数标签
        func_match = re.match(r'^([a-zA-Z_][\w]*):$', line)
        if func_match:
            current_func = func_match.group(1)
        
        # 检测备份指令：MOV.W @R12, &__SLOT_xxx_R12_Y
        # 或其他间接寻址：MOV.W offset(R12), &__SLOT_xxx_R12_Y
        backup_match = re.match(r'(\s*MOV\.W\s+)([@\d\-]*)\((R1[2-5])\)(,\s*&__SLOT_)([^_]+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        if not backup_match:
            # 尝试匹配 @R12 形式
            backup_match = re.match(r'(\s*MOV\.W\s+)@(R1[2-5])(,\s*&__SLOT_)([^_]+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        
        if backup_match and current_func:
            # 提取信息
            if len(backup_match.groups()) == 7:  # offset(R12) 形式
                prefix = backup_match.group(1)
                offset_str = backup_match.group(2)
                reg = backup_match.group(3).upper()
                middle = backup_match.group(4)
                func_name = backup_match.group(5)
                reg2 = backup_match.group(6).upper()
                reg_offset = backup_match.group(7)
                
                # 计算完整的寄存器偏移
                if offset_str:
                    try:
                        offset_val = int(offset_str)
                        reg_offset_full = f"{reg}+{int(reg_offset) + offset_val}"
                    except:
                        reg_offset_full = f"{reg}+{reg_offset}"
                else:
                    reg_offset_full = f"{reg}+{reg_offset}"
            else:  # @R12 形式
                prefix = backup_match.group(1)
                reg = backup_match.group(2).upper()
                middle = backup_match.group(3)
                func_name = backup_match.group(4)
                reg2 = backup_match.group(5).upper()
                reg_offset = backup_match.group(6)
                reg_offset_full = f"{reg}+{reg_offset}"
            
            # 查找调用者栈变量的槽位
            caller_slot = find_caller_stack_slot(current_func, reg_offset_full, call_graph, fram_slots)
            
            if caller_slot:
                # 重定向！
                # 保持原始的源操作数，只修改目标槽位
                if len(backup_match.groups()) == 7:
                    src_operand = f"{offset_str}({reg})" if offset_str else f"@{reg}"
                else:
                    src_operand = f"@{reg}"
                
                new_line = f"{prefix}{src_operand}, &{caller_slot}\n"
                output_lines.append(f"\t; ASAP重定向: {current_func}::{reg_offset_full} -> 调用者栈槽位\n")
                output_lines.append(new_line)
                redirected_count += 1
                continue
        
        # 默认：保持原样
        output_lines.append(line)
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    return redirected_count

def main():
    parser = argparse.ArgumentParser(description='Stage 5c: 重定向间接地址的备份槽位')
    parser.add_argument('--input', required=True, help='输入汇编文件')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--call-graph', required=True, help='调用图JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.call_graph, 'r') as f:
        call_graph = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 重定向槽位
    redirected = redirect_indirect_slots(args.input, call_graph, fram_slots, args.output)
    
    print(f"  ✓ 重定向了 {redirected} 个间接地址的备份槽位")

if __name__ == '__main__':
    main()













