#!/usr/bin/env python3
"""
Stage 9b: 构建函数调用图
输入: A_instrumented.s, function_info.json, candidates.json
输出: call_graph.json
"""

import json
import argparse
import re

def build_call_graph(asm_file, function_info, candidates):
    """从汇编文件构建函数调用图"""
    
    call_graph = {}
    wid_to_function = {}
    
    # 读取函数信息
    with open(function_info, 'r') as f:
        func_info = json.load(f)
    
    # 读取candidates获取WID到函数的映射
    with open(candidates, 'r') as f:
        cand = json.load(f)
        if isinstance(cand, dict):
            # candidates可能是字典格式
            for wid, data in cand.items():
                if isinstance(data, dict):
                    func = data.get('function', 'main')
                    wid_to_function[wid] = func
        elif isinstance(cand, list):
            # candidates可能是列表格式
            for item in cand:
                if isinstance(item, dict):
                    wid = item.get('wid')
                    func = item.get('function', 'main')
                    if wid:
                        wid_to_function[wid] = func
    
    # 解析汇编文件构建调用图
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    current_function = None
    context_function = None  # 上下文函数（非共享函数）
    shared_functions = {'_uart_putc', '_uart_puts', '_uart_print_uint', 'sqrt16', 'memset'}
    wid_to_context = {}  # WID → 上下文函数
    
    for line in lines:
        stripped_line = line.strip()
        
        # 识别WID标签，记录其上下文函数
        if '__WID_W' in stripped_line and stripped_line.endswith(':'):
            wid_name = stripped_line.split(':')[0].replace('__WID_', '')
            if context_function:
                wid_to_context[wid_name] = context_function
        
        # 识别函数定义（函数标签必须在行首，不缩进）
        if not line.startswith('\t') and not line.startswith(' ') and stripped_line.endswith(':'):
            func_name = stripped_line[:-1]
            
            # 跳过内部标签（以.或__开头）、WID标签、纯数字标签、ASAP内部标签
            # 也跳过注释行（以;开头）、数据标签（test_input_等）
            if (func_name.startswith('.') or func_name.startswith('__') or 
                func_name.startswith(';') or  # 跳过注释行
                func_name.startswith('test_') or  # 跳过数据标签
                '$' in func_name or func_name.isdigit() or
                func_name == '_asap_do_restore' or func_name == '__main_continue'):
                continue  # 不改变current_function
            
            if func_name == 'main':
                current_function = 'main'
                context_function = 'main'
                if 'main' not in call_graph:
                    call_graph['main'] = {'calls': [], 'stack_size': func_info.get('main', {}).get('stack_size', 0)}
            else:
                current_function = func_name
                # 只有非共享函数才更新context_function
                if func_name not in shared_functions:
                    context_function = func_name
                if current_function not in call_graph:
                    call_graph[current_function] = {
                        'calls': [],
                        'stack_size': func_info.get(current_function, {}).get('stack_size', 0)
                    }
        
        # 识别CALL指令（使用原始line，因为有tab）
        if current_function and current_function in call_graph and 'CALL' in line:
            match = re.search(r'CALL[A]?\s+#(\w+)', line)
            if match:
                callee = match.group(1)
                # 过滤掉编译器内部函数和系统函数
                # 保留用户定义的函数（包括以_开头的UART函数等）
                # 跳过ASAP恢复函数（它不是业务调用）
                # 也过滤掉memcpy（标准库函数）
                if (not callee.startswith('__mspabi_') and 
                    not callee.startswith('__gnu_') and
                    not callee.startswith('__clz') and
                    not callee.startswith('__mul') and
                    not callee.startswith('__div') and
                    not callee.startswith('__udiv') and
                    callee not in ['init', 'memset', 'memcpy', '_asap_restore', '_asap_do_restore']):
                    if callee not in call_graph[current_function]['calls']:
                        call_graph[current_function]['calls'].append(callee)
    
    # 为每个WID计算调用栈（通过DFS找到从main或_asap_do_restore到目标函数的路径）
    def find_call_path(target, graph, current='main', path=None):
        """DFS查找从current到target的调用路径"""
        if path is None:
            path = [current]
        
        if current == target:
            return path[:]
        
        if current not in graph:
            return None
        
        for callee in graph[current]['calls']:
            if callee not in path:  # 避免循环
                path.append(callee)
                result = find_call_path(target, graph, callee, path)
                if result:
                    return result
                path.pop()
        
        return None
    
    # 【新方案】为UART等共享函数，建立所有可能的调用栈
    # 对于非共享函数，使用标准路径查找
    shared_functions = {'_uart_putc', '_uart_puts', '_uart_print_uint', 'sqrt16'}
    
    # 定义递归函数：为共享函数查找完整调用栈
    def build_shared_func_stack(func, call_graph, shared_functions, memo=None):
        """为共享函数构建调用栈，递归处理被其他共享函数调用的情况"""
        if memo is None:
            memo = {}
        if func in memo:
            return memo[func]
        
        # 找到所有调用者
        all_callers = []
        for caller, info in call_graph.items():
            if func in info.get('calls', []):
                all_callers.append(caller)
        
        if not all_callers:
            # 没有调用者，回退
            result = ['main', func]
            memo[func] = result
            return result
        
        # 优先选择非共享函数调用者
        non_shared_callers = [c for c in all_callers if c not in shared_functions]
        
        if non_shared_callers:
            # 有非共享调用者，选择一个preferred调用者
            preferred = ['train', 'recognize', 'acquire_window', 'featurize']
            caller = None
            for pref in preferred:
                if pref in non_shared_callers:
                    caller = pref
                    break
            if not caller:
                caller = non_shared_callers[0]
            
            # 构建完整路径：main → ... → caller → func
            caller_path = find_call_path(caller, call_graph, 'main')
            if caller_path:
                result = caller_path + [func]
            else:
                result = ['main', caller, func]
            memo[func] = result
            return result
        else:
            # 【关键】只有共享函数调用者（例如_uart_putc被_uart_puts调用）
            # 递归查找共享调用者的调用栈
            shared_callers = [c for c in all_callers if c in shared_functions]
            if shared_callers:
                # 选择第一个共享调用者，递归构建它的调用栈
                caller = shared_callers[0]
                caller_stack = build_shared_func_stack(caller, call_graph, shared_functions, memo)
                result = caller_stack + [func]
                memo[func] = result
                return result
            else:
                # 回退
                result = ['main', func]
                memo[func] = result
                return result
    
    wid_call_stacks = {}
    shared_memo = {}  # 共享函数调用栈缓存
    
    for wid, func in wid_to_function.items():
        if func == 'main':
            wid_call_stacks[wid] = ['main']
        elif func in shared_functions:
            # 使用递归函数构建共享函数的调用栈
            wid_call_stacks[wid] = build_shared_func_stack(func, call_graph, shared_functions, shared_memo)
        else:
            # 非共享函数，直接从main搜索
            path = find_call_path(func, call_graph, 'main')
            if path:
                wid_call_stacks[wid] = path
            else:
                wid_call_stacks[wid] = ['main', func]
    
    
    return {
        'call_graph': call_graph, 
        'wid_to_function': wid_to_function,
        'wid_call_stacks': wid_call_stacks
    }


def main():
    parser = argparse.ArgumentParser(description='Stage 9b: 构建函数调用图')
    parser.add_argument('--asm', required=True, help='输入汇编文件')
    parser.add_argument('--function-info', required=True, help='函数信息JSON')
    parser.add_argument('--candidates', required=True, help='候选变量JSON')
    parser.add_argument('--output', required=True, help='输出call_graph.json')
    
    args = parser.parse_args()
    
    result = build_call_graph(args.asm, args.function_info, args.candidates)
    
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"  ✓ Stage 9b 完成")

if __name__ == '__main__':
    main()
