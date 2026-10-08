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

def find_caller_stack_slot(func_name, reg_offset, call_graph, fram_slots, debug=False):
    """找到间接地址对应的调用者栈变量的槽位
    
    Args:
        func_name: 当前函数（如 record_stats）
        reg_offset: 寄存器偏移（如 "R12+0"）
        call_graph: 调用图
        fram_slots: FRAM槽位映射
    
    Returns:
        调用者栈变量的槽位符号，如果找不到则返回None
    """
    # 从调用栈信息中推断调用者
    # call_graph.json 结构: {"wid_call_stacks": {"W080": ["main", "recognize", "record_stats"]}}
    # 我们需要找到包含 func_name 的调用栈，然后取其上一级
    caller = None
    found_call_stack = []
    wid_call_stacks = call_graph.get('wid_call_stacks', {})
    
    for wid, call_stack in wid_call_stacks.items():
        if isinstance(call_stack, list) and func_name in call_stack:
            # 找到 func_name 的位置
            idx = call_stack.index(func_name)
            if debug and func_name == 'record_stats':
                print(f"  [DEBUG] 在 {wid} 找到调用栈: {call_stack}, 索引: {idx}")
            if idx > 0:
                caller = call_stack[idx - 1]
                found_call_stack = call_stack
                break
    
    if debug:
        print(f"  [DEBUG] 查找 {func_name}::{reg_offset} 的调用者: {caller}")
    if not caller:
        return None
    
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
    
    # 改进：如果在直接调用者中找不到，向上层栈帧查找（例如main）
    # 获取完整调用栈，从直接调用者开始向上查找
    callers_to_try = []
    # 找到当前函数在调用栈中的位置
    for idx, frame in enumerate(found_call_stack):
        if frame == func_name:
            # 收集所有上层调用者（从近到远）
            for i in range(idx - 1, -1, -1):
                callers_to_try.append(found_call_stack[i])
            break
    
    if debug and func_name == 'train':
        print(f"  [DEBUG] 尝试查找调用栈: {callers_to_try}")
    
    # 依次在每个可能的调用者中查找
    for try_caller in callers_to_try:
        # 策略：遍历调用者的栈变量，找到连续的变量（可能是结构体成员）
        caller_vars = {}
        for logical_addr, slot_info in addr_to_slot.items():
            if logical_addr.startswith(f'{try_caller}::SP+'):
                parts = logical_addr.split('::SP+')
                if len(parts) == 2:
                    # 支持解析表达式，如 "7+2" → 9
                    try:
                        sp_offset = eval(parts[1])  # 安全：只包含数字和+
                    except:
                        continue  # 跳过无法解析的地址
                    caller_vars[sp_offset] = slot_info
        
        if debug and func_name == 'train':
            print(f"  [DEBUG] 检查 {try_caller} 的栈变量: {sorted(caller_vars.keys())}")
        
        # 如果调用者有栈变量，尝试匹配
        # 改进的启发式：找到连续的栈变量组（可能是结构体），其中一个成员是 target_offset
        if debug and func_name == 'record_stats':
            print(f"  [DEBUG] caller_vars: {list(caller_vars.keys())}")
        
        if caller_vars:
            base_offsets = sorted(caller_vars.keys())
            
            # 尝试找到连续的栈变量组（2字节间隔，表示结构体成员）
            # 例如：16, 18, 20 或 22, 24, 26
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
                    if debug and func_name in ['record_stats', 'train']:
                        print(f"  [DEBUG] 尝试结构体 {try_caller} base={base_offset} (连续{consecutive_count}个) + offset={offset} = {target_offset}")
                    if target_offset in caller_vars:
                        slot_symbol = caller_vars[target_offset]['slot_symbol']
                        if debug:
                            print(f"  [DEBUG] ✓ 在{try_caller}中找到槽位: {slot_symbol}")
                        return slot_symbol
            
            # 【禁用】单变量指针启发式 - 这个启发式会错误地把函数内部的局部数组
            # （如 _uart_print_uint 中的字符数组）重定向到调用者的栈变量
            # 导致循环计数器i的备份被覆盖
            # if offset == 0 and len(base_offsets) > 0:
            #     for candidate_offset in base_offsets:
            #         if candidate_offset > 0:
            #             slot_symbol = caller_vars[candidate_offset]['slot_symbol']
            #             if debug:
            #                 print(f"  [DEBUG] ✓ 单变量指针启发式：{func_name}::R12+0 -> {try_caller}::SP+{candidate_offset}")
            #             return slot_symbol
            pass  # 不做重定向，让每个函数使用自己的槽位
    
    return None

def redirect_indirect_slots(asm_file, call_graph, fram_slots, output_file, redirect_map_file=None, loop_arrays=None, candidates=None):
    """重定向间接地址的备份槽位
    
    Args:
        loop_arrays: 循环数组信息，用于跳过全局数组写入的重定向
        candidates: 候选写入信息，用于跳过array类型写入的重定向
    """
    if loop_arrays is None:
        loop_arrays = {'arrays': {}, 'writes': {}}
    if candidates is None:
        candidates = {}
    
    # 构建全局数组写入的logical_addr集合
    global_array_addrs = set()
    for wid, write_info in loop_arrays.get('writes', {}).items():
        array_name = write_info.get('array_name')
        if array_name:
            array_config = loop_arrays.get('arrays', {}).get(array_name, {})
            if array_config.get('is_global', False):
                logical_addr = write_info.get('logical_addr', '')
                if logical_addr:
                    global_array_addrs.add(logical_addr)
    
    # 从candidates中收集所有array类型写入的logical_addr
    array_type_addrs = set()
    for wid, cand_info in candidates.items():
        if cand_info.get('type') == 'array':
            logical_addr = cand_info.get('logical_addr', '')
            if logical_addr:
                array_type_addrs.add(logical_addr)
    if array_type_addrs:
        print(f"  ✓ 从candidates检测到 {len(array_type_addrs)} 个array类型写入，将跳过重定向")
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    redirected_count = 0
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
        # 格式3: MOV.B 2(R12), &__SLOT_... (char类型成员)
        # 【修复】支持 MOV.B 和 MOV.W
        backup_match = re.match(r'(\s*MOV\.[BW]\s+)(\d+)\((R1[2-5])\)(,\s*&__SLOT_)(\w+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        if not backup_match:
            # 尝试匹配 @R12 形式
            backup_match = re.match(r'(\s*MOV\.[BW]\s+)@(R1[2-5])(,\s*&__SLOT_)(\w+)_(R1[2-5])_(\d+)', line, re.IGNORECASE)
        
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
                
                # offset_str 是汇编指令中的偏移（如 "2" in "2(R12)"）
                # reg_offset_from_slot 是槽位名称中的偏移（如 "R12_2"）
                # 它们应该相同（都是字节偏移）
                reg_offset_full = f"{reg}+{offset_str}"
            else:  # @R12 形式
                prefix = backup_match.group(1)
                reg = backup_match.group(2).upper()
                middle = backup_match.group(3)
                func_name = backup_match.group(4)
                reg2 = backup_match.group(5).upper()
                reg_offset = backup_match.group(6)
                reg_offset_full = f"{reg}+{reg_offset}"
            
            # 构建当前写入的logical_addr
            current_logical_addr = f"{current_func}::{reg_offset_full}"
            
            # 【关键修复】如果是全局数组写入或array类型写入，跳过重定向
            if current_logical_addr in global_array_addrs or current_logical_addr in array_type_addrs:
                output_lines.append(line)
                continue
            
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
        
        # 默认：保持原样
        output_lines.append(line)
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    # 保存重定向映射
    if redirect_map_file:
        with open(redirect_map_file, 'w') as f:
            json.dump(redirect_map, f, indent=2)
    
    return redirected_count

def main():
    parser = argparse.ArgumentParser(description='Stage 5d: 重定向间接地址的备份槽位')
    parser.add_argument('--input', required=True, help='输入汇编文件')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--call-graph', required=True, help='调用图JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--redirect-map', help='输出重定向映射JSON')
    parser.add_argument('--loop-arrays', help='循环数组JSON（用于跳过全局数组重定向）')
    parser.add_argument('--candidates', help='候选写入JSON（用于跳过array类型重定向）')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.call_graph, 'r') as f:
        call_graph = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 加载循环数组信息（可选）
    loop_arrays = None
    if args.loop_arrays:
        try:
            with open(args.loop_arrays, 'r') as f:
                loop_arrays = json.load(f)
            print(f"  ✓ 加载循环数组信息，将跳过全局数组重定向")
        except FileNotFoundError:
            print(f"  ⚠ 循环数组文件不存在，不跳过重定向")
    
    # 加载候选写入信息（可选）
    candidates = {}
    candidates_file = args.candidates or 'build/candidates.json'
    try:
        with open(candidates_file, 'r') as f:
            candidates = json.load(f)
    except FileNotFoundError:
        pass
    
    # 重定向槽位
    redirected = redirect_indirect_slots(args.input, call_graph, fram_slots, args.output, args.redirect_map, loop_arrays, candidates)
    
    print(f"  ✓ 重定向了 {redirected} 个间接地址的备份槽位")
    if args.redirect_map:
        print(f"  ✓ 重定向映射保存到: {args.redirect_map}")

if __name__ == '__main__':
    main()

