#!/usr/bin/env python3
"""
Stage 2.5: 分析函数调用和参数传递
识别"栈地址参数"（调用者传递栈上数组/结构体地址给被调用者）

输入: build/A_idempotent.s, build/function_info.json
输出: build/call_info.json

用于后续stage3检测间接栈写入：
- 如果被调用函数通过参数寄存器（R12-R15）间接写入
- 且该参数是调用者栈上的地址
- 则该写入实际上是对调用者栈的写入
"""
import argparse
import json
import re

def analyze_call_sites(asm_file, function_info):
    """
    分析所有函数调用点，识别栈地址参数
    
    返回格式:
    {
        'function_params': {
            'insert': [
                {
                    'reg': 'R12',
                    'type': 'stack_address',
                    'source_func': 'main',
                    'offset': 0,
                    'logical_addr': 'main::SP+0'
                }
            ]
        },
        'call_sites': {
            'main': [
                {
                    'callee': 'insert',
                    'line': 518,
                    'params': {...}
                }
            ]
        }
    }
    """
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 构建函数行号映射
    func_line_map = {}
    func_ranges = {}
    for func_name, info in function_info.items():
        start = info['start_line']
        end = info.get('end_line', start + 500)
        func_ranges[func_name] = (start, end)
        for line_num in range(start, end + 1):
            func_line_map[line_num] = func_name
    
    # 结果结构
    function_params = {}  # {callee: [param_info]}
    call_sites = {}  # {caller: [call_info]}
    
    current_func = None
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # 更新当前函数
        current_func = func_line_map.get(i, current_func)
        
        # 检测函数调用 CALL #func_name
        call_match = re.search(r'CALL\s+#(\w+)', stripped, re.IGNORECASE)
        if not call_match or not current_func:
            continue
        
        callee = call_match.group(1)
        
        # 跳过系统函数
        if callee.startswith('__') or callee in ['memset', 'memcpy', 'printf', 'puts']:
            continue
        
        # 往前查找参数准备（最多15行）
        param_info = analyze_param_preparation(lines, i, current_func, function_info)
        
        if param_info:
            # 记录调用点
            if current_func not in call_sites:
                call_sites[current_func] = []
            call_sites[current_func].append({
                'callee': callee,
                'line': i,
                'params': param_info
            })
            
            # 记录被调用函数的参数信息（合并多个调用点）
            if callee not in function_params:
                function_params[callee] = []
            
            for reg, info in param_info.items():
                # 检查是否已存在相同参数
                existing = [p for p in function_params[callee] if p['reg'] == reg]
                if not existing:
                    function_params[callee].append({
                        'reg': reg,
                        'type': info['type'],
                        'source_func': info['source_func'],
                        'offset': info['offset'],
                        'logical_addr': info['logical_addr']
                    })
    
    return {
        'function_params': function_params,
        'call_sites': call_sites
    }

def analyze_param_preparation(lines, call_line_idx, caller_func, function_info):
    """
    分析调用前的参数准备指令，识别栈地址参数
    
    模式1: MOV.W R1, R12 （直接传递栈指针）
           → R12 = caller::SP+0
    
    模式2: MOV.W R1, R12
           ADD.W #offset, R12
           → R12 = caller::SP+offset
    
    模式3: MOV.W #base, R12
           ADD.W R1, R12
           ADD.W #adjust, R12
           → R12 = caller::SP+(base+adjust)
    
    返回: {reg: {type, source_func, offset, logical_addr}}
    """
    lookback = 15
    start = max(0, call_line_idx - lookback - 1)
    context_lines = [(start + j + 1, lines[start + j]) for j in range(call_line_idx - start - 1)]
    
    param_info = {}
    
    # 追踪每个参数寄存器的来源
    for reg in ['R12', 'R13', 'R14', 'R15']:
        result = trace_register_to_stack(context_lines, reg, caller_func, function_info)
        if result:
            param_info[reg] = result
    
    return param_info

def trace_register_to_stack(context_lines, target_reg, caller_func, function_info):
    """
    追踪寄存器是否来自栈地址
    
    返回: {type, source_func, offset, logical_addr} 或 None
    """
    # 从后往前搜索，找到最后一次对target_reg的赋值
    reg_assignments = []
    
    for line_num, line in reversed(context_lines):
        stripped = line.strip()
        
        # 模式1: MOV.W R1, Rx （直接传递栈指针）
        match = re.match(rf'MOV\.?[WB]?\s+R1,\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            reg_assignments.append(('direct_sp', line_num, 0))
            break
        
        # 模式2: MOV.W offset(R1), Rx （传递栈上变量的值，不是地址）
        match = re.match(rf'MOV\.?[WB]?\s+(\d+)\(R1\),\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            # 这是值传递，不是地址传递
            break
        
        # 模式3: ADD.W #offset, Rx （在栈指针基础上加偏移）
        match = re.match(rf'ADD\.?[WB]?\s+#(-?\d+),\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            offset = int(match.group(1))
            reg_assignments.append(('add_offset', line_num, offset))
            continue
        
        # 模式4: ADD.W R1, Rx （加上栈指针）
        match = re.match(rf'ADD\.?[WB]?\s+R1,\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            reg_assignments.append(('add_sp', line_num, 0))
            continue
        
        # 模式5: MOV.W #const, Rx （加载常数）
        match = re.match(rf'MOV\.?[WB]?\s+#(\d+),\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            const = int(match.group(1))
            reg_assignments.append(('load_const', line_num, const))
            continue
        
        # 模式6: SUB.W #offset, Rx （减去偏移）
        match = re.match(rf'SUB\.?[WB]?\s+#(-?\d+),\s+{target_reg}', stripped, re.IGNORECASE)
        if match:
            offset = -int(match.group(1))
            reg_assignments.append(('add_offset', line_num, offset))
            continue
    
    # 分析赋值序列，判断是否是栈地址
    if not reg_assignments:
        return None
    
    # 情况1: 直接 MOV R1, Rx
    if reg_assignments[0][0] == 'direct_sp':
        # 检查后续是否有 ADD #offset
        total_offset = 0
        for assign in reg_assignments[1:]:
            if assign[0] == 'add_offset':
                total_offset += assign[2]
        
        return {
            'type': 'stack_address',
            'source_func': caller_func,
            'offset': total_offset,
            'logical_addr': f"{caller_func}::SP+{total_offset}"
        }
    
    # 情况2: MOV #const, Rx; ADD R1, Rx; ADD #adjust, Rx
    # 这种模式常见于大偏移计算
    has_add_sp = any(a[0] == 'add_sp' for a in reg_assignments)
    has_load_const = any(a[0] == 'load_const' for a in reg_assignments)
    
    if has_add_sp:
        total_offset = 0
        for assign in reg_assignments:
            if assign[0] == 'load_const':
                total_offset += assign[2]
            elif assign[0] == 'add_offset':
                total_offset += assign[2]
        
        # 调整：考虑caller的栈帧大小
        caller_stack = function_info.get(caller_func, {}).get('stack_size', 0)
        
        return {
            'type': 'stack_address',
            'source_func': caller_func,
            'offset': total_offset,
            'logical_addr': f"{caller_func}::SP+{total_offset}"
        }
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Stage 2.5: 分析函数调用和参数传递')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--output', default='build/call_info.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载函数信息
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    # 分析调用点
    call_info = analyze_call_sites(args.asm_file, function_info)
    
    # 输出结果
    with open(args.output, 'w') as f:
        json.dump(call_info, f, indent=2)
    
    # 统计
    total_params = sum(len(params) for params in call_info['function_params'].values())
    stack_addr_params = sum(
        1 for params in call_info['function_params'].values()
        for p in params if p['type'] == 'stack_address'
    )
    
    print(f"  ✓ 分析完成:")
    print(f"    - 识别到 {len(call_info['function_params'])} 个被调用函数的参数信息")
    print(f"    - 共 {total_params} 个参数，其中 {stack_addr_params} 个栈地址参数")
    
    # 显示详情
    if stack_addr_params > 0:
        print(f"  ✓ 栈地址参数详情:")
        for func, params in call_info['function_params'].items():
            for p in params:
                if p['type'] == 'stack_address':
                    print(f"    - {func}({p['reg']}) ← {p['logical_addr']}")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()
















