#!/usr/bin/env python3
"""
Stage 2c: 消除间接寻址，转换为直接栈寻址
解决间接寻址断电后寄存器丢失的问题
"""
import argparse
import re
import json

def parse_function_body(lines, start_idx, end_idx):
    """提取函数体"""
    return lines[start_idx:end_idx]

def uses_indirect_addressing(func_lines):
    """检查函数是否使用非R1的间接寻址"""
    patterns = [
        r'@R([2-9]|1[0-5])',           # @R2-@R15
        r'[+-]?\d+\(R([2-9]|1[0-5])\)', # offset(R2-R15)
    ]
    for line in func_lines:
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
    return False

def is_simple_indirect_function_OLD(func_lines, debug=False):
    """检查函数是否适合转换（R12只用作参数，不被重新赋值为其他指针）
    
    适合转换的条件：
    1. 函数入口保存R12到栈：MOV.W R12, offset(R1)
    2. 后续只从栈重新加载R12：MOV.W offset(R1), R12
    3. 不从其他地方（如局部变量）加载指针到R12
    """
    # 找到R12保存的栈位置
    r12_stack_offset = None
    for line in func_lines[:25]:  # 扩大到前25行，包含prologue
        match = re.search(r'MOV\.?[BW]?\s+R12,\s+(\d+)\(R1\)', line, re.IGNORECASE)
        if match:
            r12_stack_offset = int(match.group(1))
            if debug:
                print(f"      R12保存在 {r12_stack_offset}(R1)")
            break
    
    if r12_stack_offset is None:
        if debug:
            print(f"      未找到R12保存位置")
        return False
    
    # 检查是否有其他地方加载指针到R12（除了从保存位置重新加载）
    for line in func_lines[10:]:  # 跳过函数入口
        # 检测 MOV.W 某处, R12（加载到R12）
        mov_to_r12 = re.search(r'MOV\.?[BW]?\s+([^,]+),\s+R12', line, re.IGNORECASE)
        if mov_to_r12:
            source = mov_to_r12.group(1).strip()
            # 允许的来源：从保存位置重新加载、从其他寄存器
            if source == f'{r12_stack_offset}(R1)':
                continue  # 从保存位置重新加载，OK
            if re.match(r'R\d+', source, re.IGNORECASE):
                continue  # 从寄存器加载（如R13），通常是临时计算，OK
            if re.match(r'#', source):
                continue  # 立即数，OK
            if re.match(r'@R\d+', source, re.IGNORECASE):
                continue  # 间接寻址（如@R12），是解引用不是重新赋值指针，OK
            if re.match(r'[+-]?\d+\(R\d+\)', source, re.IGNORECASE):
                # 索引寻址（如2(R12)），也是解引用，OK
                # 但如果是从其他栈变量加载（如20(R1)），需要检查是否是指针
                if re.match(r'\d+\(R1\)', source):
                    # 从栈变量加载到R12，可能是加载另一个指针
                    # 需要排除：这个栈变量不是R12的保存位置
                    offset_match = re.match(r'(\d+)\(R1\)', source)
                    if offset_match:
                        offset = int(offset_match.group(1))
                        if offset != r12_stack_offset:
                            if debug:
                                print(f"      ❌ {line.strip()}: 从 {offset}(R1) 加载，不是保存位置 {r12_stack_offset}(R1)")
                            return False  # 从其他栈位置加载指针，不适合转换！
                continue
    
    if debug:
        print(f"      ✓ 适合转换")
    return True

def get_param_reg_mapping(func_lines):
    """分析函数入口，找到参数寄存器保存到栈的映射
    返回: {reg: stack_offset}
    例如: {'R12': 2, 'R13': 0} 表示 R12保存在2(R1), R13保存在0(R1)
    """
    mapping = {}
    for line in func_lines[:20]:  # 只看前20行（函数入口）
        # 匹配 MOV.W R12, offset(R1)
        match = re.search(r'MOV\.?[BW]?\s+(R1[2-5]),\s+(\d+)\(R1\)', line, re.IGNORECASE)
        if match:
            reg = match.group(1).upper()
            offset = int(match.group(2))
            mapping[reg] = offset
    return mapping

def analyze_call_sites(lines, function_info):
    """分析函数调用点，找到参数来源
    返回: {func_name: {caller: {param_reg: (caller_var_offset, caller_stack_size)}}}
    """
    call_info = {}
    
    current_func = None
    for i, line in enumerate(lines):
        # 检测函数标签
        func_match = re.match(r'^(\w+):$', line.strip())
        if func_match:
            func_name = func_match.group(1)
            if func_name in function_info:
                current_func = func_name
        
        # 检测函数调用
        call_match = re.search(r'CALL\s+#(\w+)', line, re.IGNORECASE)
        if call_match and current_func:
            callee = call_match.group(1)
            
            # 往前查找参数准备（最多10行）
            param_prep = {}
            for j in range(max(0, i-10), i):
                prev_line = lines[j]
                
                # 模式1: MOV.W R1, R12; ADD.W #offset, R12
                mov_r1_match = re.search(r'MOV\.?[BW]?\s+R1,\s+(R1[2-5])', prev_line, re.IGNORECASE)
                if mov_r1_match:
                    temp_reg = mov_r1_match.group(1).upper()
                    # 查找后续的 ADD
                    for k in range(j+1, min(j+5, i)):
                        add_match = re.search(rf'ADD\.?[BW]?\s+#(\d+),\s+{temp_reg}', lines[k], re.IGNORECASE)
                        if add_match:
                            offset = int(add_match.group(1))
                            param_prep[temp_reg] = offset
                            break
            
            if param_prep and current_func in function_info:
                if callee not in call_info:
                    call_info[callee] = {}
                call_info[callee][current_func] = {
                    'params': param_prep,
                    'caller_stack': function_info[current_func].get('stack_size', 0)
                }
    
    return call_info

def calculate_absolute_offset(param_reg, call_info, func_name, caller_name, callee_stack_size):
    """计算变量在被调用函数栈中的绝对偏移
    
    公式: caller_var_offset + return_addr_size(2) + callee_stack_size
    """
    if func_name not in call_info:
        return None
    if caller_name not in call_info[func_name]:
        return None
    
    caller_info = call_info[func_name][caller_name]
    if param_reg not in caller_info['params']:
        return None
    
    caller_var_offset = caller_info['params'][param_reg]
    # 公式：调用者变量偏移 + 返回地址(2字节) + 被调用函数栈帧大小
    absolute_offset = caller_var_offset + 2 + callee_stack_size
    
    return absolute_offset

def replace_indirect_addressing(func_lines, param_mapping, base_offsets):
    """替换间接寻址为直接栈寻址
    
    param_mapping: {reg: stack_offset} - 参数在当前函数栈中的位置
    base_offsets: {reg: caller_var_offset} - 参数指向的变量在调用者中的偏移
    """
    new_lines = []
    
    for line in func_lines:
        new_line = line
        
        # 替换 @R12 -> absolute_offset(R1)
        for reg, base_offset in base_offsets.items():
            if base_offset is None:
                continue
            
            # 模式1: @R12
            pattern1 = rf'@{reg}\b'
            if re.search(pattern1, new_line, re.IGNORECASE):
                new_line = re.sub(pattern1, f'{base_offset}(R1)', new_line, flags=re.IGNORECASE)
            
            # 模式2: offset(R12)
            pattern2 = rf'([+-]?\d+)\({reg}\)'
            def replace_offset(match):
                offset = int(match.group(1))
                total_offset = base_offset + offset
                return f'{total_offset}(R1)'
            new_line = re.sub(pattern2, replace_offset, new_line, flags=re.IGNORECASE)
        
        new_lines.append(new_line)
    
    return new_lines

def eliminate_indirect_addressing(input_asm, output_asm, function_info_file):
    """主函数：消除间接寻址"""
    
    # 加载函数信息
    with open(function_info_file, 'r') as f:
        function_info = json.load(f)
    
    with open(input_asm, 'r') as f:
        lines = f.readlines()
    
    # 分析调用点
    call_info = analyze_call_sites(lines, function_info)
    
    print(f"  分析到 {len(call_info)} 个被调用的函数")
    for func, callers in call_info.items():
        print(f"    {func}: 被 {list(callers.keys())} 调用")
    
    # 处理每个函数
    output_lines = []
    transform_count = 0
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 检测函数标签
        func_match = re.match(r'^(\w+):$', line.strip())
        if func_match:
            func_name = func_match.group(1)
            
            # 找到函数结束位置
            func_end = i + 1
            for j in range(i + 1, len(lines)):
                if re.match(r'^(\w+):$', lines[j].strip()):
                    func_end = j
                    break
                if re.search(r'\bret\b', lines[j], re.IGNORECASE):
                    func_end = j + 1
                    # 继续查找，可能有多个return
            
            func_lines = lines[i:func_end]
            
            # 检查是否使用间接寻址
            if func_name in function_info and uses_indirect_addressing(func_lines):
                print(f"  ⚠️  {func_name}: 使用间接寻址")
                
                # 检查是否适合转换（R12只用作单一参数指针）
                debug_funcs = ['record_stats', 'classify', 'featurize']
                debug = func_name in debug_funcs
                if not is_simple_indirect_function_OLD(func_lines, debug=debug):
                    print(f"    ✗ {func_name}: R12被多次重新赋值为不同指针，跳过转换")
                    output_lines.extend(func_lines)
                    i = func_end
                    continue
                
                # 获取参数映射
                param_mapping = get_param_reg_mapping(func_lines)
                
                # 计算绝对偏移（如果有调用信息）
                base_offsets = {}
                if func_name in call_info:
                    for caller_name, caller_info in call_info[func_name].items():
                        callee_stack = function_info[func_name].get('stack_size', 0)
                        for param_reg in param_mapping.keys():
                            abs_offset = calculate_absolute_offset(
                                param_reg, call_info, func_name, 
                                caller_name, callee_stack
                            )
                            if abs_offset is not None:
                                base_offsets[param_reg] = abs_offset
                                print(f"    ✓ {param_reg} -> {abs_offset}(R1) (通过 {caller_name})")
                                break  # 只处理第一个调用者
                
                # 替换间接寻址
                if base_offsets:
                    new_func_lines = replace_indirect_addressing(func_lines, param_mapping, base_offsets)
                    output_lines.extend(new_func_lines)
                    transform_count += 1
                    i = func_end
                    continue
            
            # 未转换的函数，直接输出
            output_lines.extend(func_lines)
            i = func_end
        else:
            output_lines.append(line)
            i += 1
    
    # 写入输出
    with open(output_asm, 'w') as f:
        f.writelines(output_lines)
    
    return transform_count

def main():
    parser = argparse.ArgumentParser(description='Stage 2c: 消除间接寻址')
    parser.add_argument('input', help='输入汇编文件')
    parser.add_argument('--function-info', required=True, help='函数信息JSON')
    parser.add_argument('--output', default='build/A_direct_addr.s', help='输出汇编文件')
    
    args = parser.parse_args()
    
    count = eliminate_indirect_addressing(args.input, args.output, args.function_info)
    
    print(f"  ✓ 间接寻址消除完成:")
    print(f"    - 转换了 {count} 个函数")
    print(f"    - 输出: {args.output}")

if __name__ == '__main__':
    main()

