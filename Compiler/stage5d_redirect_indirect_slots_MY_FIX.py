#!/usr/bin/env python3
"""
Stage 5d: 重定向间接地址的备份槽位（修复版）
【修复】只重定向真正指向调用者栈的间接地址，不重定向局部变量的参数指针

问题：
  featurize(&features, ...) 中：
  - train调用：features = train::SP+2/4
  - recognize调用：features = recognize::SP+X/Y
  
  不能将所有 featurize::R13+0 都重定向到 main::SP+130！
  
解决：
  只重定向那些【在多次调用中指向同一位置】的间接地址
  例如：train中的 classModel 数组（在main栈上）
"""
import argparse
import json
import re

def is_safe_to_redirect(func_name, reg_offset, caller, call_graph):
    """判断一个间接地址是否可以安全重定向
    
    安全重定向的条件：
    1. 这个变量在所有调用上下文中都指向同一个调用者栈位置
    2. 不是局部变量的参数指针（每次调用指向不同位置）
    
    启发式判断：
    - 如果一个函数（如featurize）被多个不同的函数调用
    - 并且每个调用者都有自己的features局部变量
    - 那么这个指针参数不应该被重定向
    """
    # 获取所有调用该函数的地方
    wid_call_stacks = call_graph.get('wid_call_stacks', {})
    
    callers = set()
    for wid, call_stack in wid_call_stacks.items():
        if isinstance(call_stack, list) and func_name in call_stack:
            idx = call_stack.index(func_name)
            if idx > 0:
                callers.add(call_stack[idx - 1])
    
    # 如果有多个不同的调用者，说明这可能是一个参数指针
    # 不应该重定向（因为每个调用者可能传递不同的局部变量地址）
    if len(callers) > 1:
        return False
    
    # 【特殊规则】：featurize的features参数不重定向
    # 因为它在train和recognize中都被调用，指向各自的局部变量
    if func_name == 'featurize' and reg_offset.startswith('R13+'):
        return False
    
    # 【特殊规则】：如果调用者是train或recognize，
    # 并且被调用的函数是它们的子函数（如featurize），
    # 那么第一个参数（R12/R13）很可能是局部变量指针，不重定向
    if caller in ['train', 'recognize']:
        if func_name in ['featurize', 'classify', 'record_stats']:
            if reg_offset.startswith(('R12+', 'R13+')):
                return False
    
    return True

def find_caller_stack_slot(func_name, reg_offset, call_graph, fram_slots, debug=False):
    """找到间接地址对应的调用者栈变量的槽位
    
    Args:
        func_name: 当前函数（如 record_stats）
        reg_offset: 寄存器偏移（如 "R12+0")
        call_graph: 调用图
        fram_slots: FRAM槽位映射
    
    Returns:
        (调用者名称, 槽位符号)，如果找不到则返回(None, None)
    """
    # 从调用栈信息中推断调用者
    caller = None
    wid_call_stacks = call_graph.get('wid_call_stacks', {})
    
    for wid, call_stack in wid_call_stacks.items():
        if isinstance(call_stack, list) and func_name in call_stack:
            # 找到 func_name 的位置
            idx = call_stack.index(func_name)
            if debug and func_name == 'record_stats':
                print(f"  [DEBUG] 在 {wid} 找到调用栈: {call_stack}, 索引: {idx}")
            if idx > 0:
                caller = call_stack[idx - 1]
                break
    
    if debug:
        print(f"  [DEBUG] 查找 {func_name}::{reg_offset} 的调用者: {caller}")
    if not caller:
        return None, None
    
    # 检查是否应该重定向
    if not is_safe_to_redirect(func_name, reg_offset, caller, call_graph):
        if debug:
            print(f"  [DEBUG] ✗ 不安全重定向: {func_name}::{reg_offset}")
        return None, None
    
    # 解析寄存器偏移
    if '+' in reg_offset:
        reg_name, offset_str = reg_offset.split('+')
        offset = int(offset_str)
    else:
        reg_name = reg_offset
        offset = 0
    
    # 在调用者的栈变量中查找可能的对应关系
    addr_to_slot = fram_slots.get('addr_to_slot', {})
    
    # 查找调用者的栈变量，看哪个可能对应这个间接地址
    caller_vars = {}
    for logical_addr, slot_info in addr_to_slot.items():
        if logical_addr.startswith(f'{caller}::SP+'):
            parts = logical_addr.split('::SP+')
            if len(parts) == 2:
                sp_offset = int(parts[1])
                caller_vars[sp_offset] = slot_info
    
    # 如果调用者有栈变量，尝试匹配
    if debug and func_name == 'record_stats':
        print(f"  [DEBUG] caller_vars: {list(caller_vars.keys())}")
    
    if caller_vars:
        base_offsets = sorted(caller_vars.keys())
        
        # 尝试找到连续的栈变量组（2字节间隔，表示结构体成员）
        for i, base_offset in enumerate(base_offsets):
            # 检查是否形成连续组
            consecutive_count = 1
            for j in range(i + 1, len(base_offsets)):
                if base_offsets[j] == base_offset + consecutive_count * 2:
                    consecutive_count += 1
                else:
                    break
            
            # 如果有至少2个连续成员，可能是结构体
            if consecutive_count >= 2:
                target_offset = base_offset + offset
                if debug and func_name == 'record_stats':
                    print(f"  [DEBUG] 尝试结构体 base={base_offset} (连续{consecutive_count}个) + offset={offset} = {target_offset}")
                if target_offset in caller_vars:
                    slot_symbol = caller_vars[target_offset]['slot_symbol']
                    if debug:
                        print(f"  [DEBUG] ✓ 找到槽位: {slot_symbol}")
                    return caller, slot_symbol
    
    return None, None

def redirect_indirect_slots(asm_file, call_graph, fram_slots, output_file, redirect_map_file=None):
    """重定向间接地址的备份槽位"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    redirected_count = 0
    skipped_count = 0
    current_func = None
    redirect_map = {}  # {原始logical_addr: 目标logical_addr}
    
    for i, line in enumerate(lines):
        # 检测函数标签（排除WID标签）
        func_match = re.match(r'^([a-zA-Z_][\w]*):$', line)
        if func_match:
            func_name = func_match.group(1)
            # 跳过WID标签，只保留真实函数名
            if not func_name.startswith('__WID_'):
                current_func = func_name
        
        # 检测备份指令：
        # 格式1: MOV.W @R12, &__SLOT_record_stats_R12_0
        # 格式2: MOV.W 2(R12), &__SLOT_record_stats_R12_2
        backup_match = re.match(r'(\s*MOV\.W\s+)(\d+)\((R1[2-5])\)(,\s*&__SLOT_)(\w+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        if not backup_match:
            # 尝试匹配 @R12 形式
            backup_match = re.match(r'(\s*MOV\.W\s+)@(R1[2-5])(,\s*&__SLOT_)(\w+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        
        if backup_match and current_func:
            # 提取信息
            if len(backup_match.groups()) == 7:  # offset(R12) 形式
                prefix = backup_match.group(1)
                offset_str = backup_match.group(2)
                reg = backup_match.group(3).upper()
                middle = backup_match.group(4)
                func_name = backup_match.group(5)
                reg2 = backup_match.group(6).upper()
                reg_offset_from_slot = backup_match.group(7)
                
                reg_offset_full = f"{reg}+{offset_str}"
            else:  # @R12 形式
                prefix = backup_match.group(1)
                reg = backup_match.group(2).upper()
                middle = backup_match.group(3)
                func_name = backup_match.group(4)
                reg2 = backup_match.group(5).upper()
                reg_offset = backup_match.group(6)
                reg_offset_full = f"{reg}+{reg_offset}"
                offset_str = reg_offset
            
            # 查找调用者栈变量的槽位
            caller, caller_slot = find_caller_stack_slot(current_func, reg_offset_full, call_graph, fram_slots)
            
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
                
                # 记录重定向映射
                original_logical_addr = f"{func_name}::{reg_offset_full}"
                # 从caller_slot中提取目标logical_addr
                # __SLOT_recognize_SP_16 -> recognize::SP+16
                target_match = re.match(r'__SLOT_(\w+)_SP_(\d+)', caller_slot)
                if target_match:
                    target_func = target_match.group(1)
                    target_offset = target_match.group(2)
                    target_logical_addr = f"{target_func}::SP+{target_offset}"
                    redirect_map[original_logical_addr] = target_logical_addr
                
                redirected_count += 1
                continue
            else:
                # 不重定向，保持原样（使用原始槽位）
                skipped_count += 1
        
        # 默认：保持原样
        output_lines.append(line)
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    # 保存重定向映射
    if redirect_map_file:
        with open(redirect_map_file, 'w') as f:
            json.dump(redirect_map, f, indent=2)
    
    return redirected_count, skipped_count

def main():
    parser = argparse.ArgumentParser(description='Stage 5d: 重定向间接地址的备份槽位（修复版）')
    parser.add_argument('--input', required=True, help='输入汇编文件')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--call-graph', required=True, help='调用图JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--redirect-map', help='输出重定向映射JSON')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.call_graph, 'r') as f:
        call_graph = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 重定向槽位
    redirected, skipped = redirect_indirect_slots(args.input, call_graph, fram_slots, args.output, args.redirect_map)
    
    print(f"  ✓ 重定向了 {redirected} 个间接地址的备份槽位")
    print(f"  ⚠ 跳过了 {skipped} 个不安全的重定向（使用原始槽位）")
    if args.redirect_map:
        print(f"  ✓ 重定向映射保存到: {args.redirect_map}")

if __name__ == '__main__':
    main()

