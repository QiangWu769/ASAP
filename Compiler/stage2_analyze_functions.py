#!/usr/bin/env python3
"""
Stage 2: 分析函数信息
输入: build/A_sym.s
输出: build/function_info.json
"""
import argparse
import json
import re

def analyze_functions(asm_file):
    """分析汇编文件中的函数边界和栈帧大小"""
    functions = {}
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # 1. 识别函数开始: 标签后跟冒号，且不是局部标签(.L开头)
        func_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*):$', stripped)
        if func_match:
            func_name = func_match.group(1)
            # 跳过局部标签
            if not func_name.startswith('.L'):
                functions[func_name] = {
                    'start_line': i,
                    'end_line': None,
                    'stack_size': 0
                }
        
        # 2. 识别函数结束: .size指令
        size_match = re.match(r'\.size\s+([a-zA-Z_][a-zA-Z0-9_]*),', stripped)
        if size_match:
            func_name = size_match.group(1)
            if func_name in functions:
                functions[func_name]['end_line'] = i
    
    # 3. 识别栈帧大小: 扫描每个函数内的SUB.W/PUSHM/PUSH指令
    for func_name, info in functions.items():
        if info['end_line'] is None:
            continue
        
        saved_regs_size = 0  # 保存寄存器占用的栈空间
        locals_size = 0      # 局部变量占用的栈空间
        
        for line_num in range(info['start_line'], info['end_line'] + 1):
            if line_num > len(lines):
                break
            line = lines[line_num - 1]
            
            # 匹配 SUB.W #N, R1 或 SUB.W #N, SP （局部变量）
            stack_match = re.search(r'SUB\.W\s+#(\d+),\s*(?:R1|SP)', line, re.IGNORECASE)
            if stack_match:
                locals_size = max(locals_size, int(stack_match.group(1)))
            
            # 匹配 PUSHM.W #N, Rx （保存N个寄存器，每个2字节）
            pushm_match = re.search(r'PUSHM\.W\s+#(\d+),', line, re.IGNORECASE)
            if pushm_match:
                saved_regs_size += int(pushm_match.group(1)) * 2
            
            # 匹配 PUSH.W Rx 或 PUSH Rx （保存1个寄存器，2字节）
            if re.search(r'PUSH(?:\.W)?\s+R\d+', line, re.IGNORECASE):
                saved_regs_size += 2
        
        # 总栈帧大小 = 保存的寄存器 + 局部变量
        info['stack_size'] = saved_regs_size + locals_size
    
    # 4. 删除没有找到结束标记的函数（可能是外部符号）
    functions = {k: v for k, v in functions.items() if v['end_line'] is not None}
    
    return functions

def main():
    parser = argparse.ArgumentParser(description='Stage 2: 分析函数信息')
    parser.add_argument('asm_file', help='汇编文件路径')
    parser.add_argument('--output', default='build/function_info.json', help='输出JSON')
    
    args = parser.parse_args()
    
    functions = analyze_functions(args.asm_file)
    
    # 输出结果
    with open(args.output, 'w') as f:
        json.dump(functions, f, indent=2)
    
    print(f"  ✓ 识别到 {len(functions)} 个函数:")
    for name, info in list(functions.items())[:10]:  # 只显示前10个
        print(f"    {name}: 栈帧={info['stack_size']}字节, 行{info['start_line']}-{info['end_line']}")
    if len(functions) > 10:
        print(f"    ... 还有 {len(functions) - 10} 个函数")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()
