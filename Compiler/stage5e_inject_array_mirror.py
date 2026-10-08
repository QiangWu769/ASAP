#!/usr/bin/env python3
"""
Stage 5e: 注入循环数组镜像写入代码

对于循环数组写入：
1. 在函数入口保存数组基地址
2. 在每次数组写入后，同步写入FRAM镜像

输入: build/A_instrumented.s, build/loop_arrays.json, build/fram_slots.json
输出: build/A_array_mirror.s
"""

import argparse
import json
import re
from pathlib import Path

def inject_array_mirror_code(asm_file, loop_arrays_file, fram_slots_file, output_file, candidates_file='build/candidates.json'):
    """注入数组镜像写入代码"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    with open(loop_arrays_file, 'r') as f:
        loop_arrays = json.load(f)
    
    with open(fram_slots_file, 'r') as f:
        fram_slots = json.load(f)
    
    # 加载candidates以获取每个WID的offset信息
    candidates = {}
    try:
        with open(candidates_file, 'r') as f:
            candidates = json.load(f)
    except:
        print(f"  警告: 无法加载 {candidates_file}，offset将默认为0")
    
    array_mirrors = fram_slots.get('array_mirrors', {})
    base_slots = fram_slots.get('array_base_slots', {})
    loop_writes = loop_arrays.get('writes', {})  # 标记的循环数组写入
    
    if not array_mirrors:
        print("  没有循环数组需要处理")
        with open(output_file, 'w') as f:
            f.writelines(lines)
        return
    
    output_lines = []
    current_func = None
    injected_base_save = set()  # 已注入基地址保存的函数
    mirror_injected = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        output_lines.append(line)
        
        # 检测函数入口
        func_match = re.match(r'^(\w+):', line)
        if func_match:
            func_name = func_match.group(1)
            if not func_name.startswith('.') and not func_name.startswith('__'):
                current_func = func_name
        
        # 在callee函数入口保存数组基地址
        for array_name, config in array_mirrors.items():
            if config.get('param_reg') and current_func:
                # 检查当前函数是否是接收数组参数的函数
                callee_funcs = loop_arrays['arrays'].get(array_name, {}).get('callee_funcs', [])
                if current_func in callee_funcs and current_func not in injected_base_save:
                    # 检测函数prologue结束（SUB.W #xx, R1 之后）
                    if 'SUB.W' in line and 'R1' in line:
                        param_reg = config['param_reg']
                        base_symbol = base_slots.get(array_name, {}).get('symbol', f'__BASE_{array_name}')
                        
                        # 注入基地址保存代码
                        save_code = f"\t; ===== 保存{array_name}数组基地址 =====\n"
                        save_code += f"\tMOV.W {param_reg}, &{base_symbol}\n"
                        output_lines.append(save_code)
                        
                        injected_base_save.add(current_func)
                        print(f"  注入 {current_func} 入口: 保存 {array_name} 基地址 ({param_reg} → {base_symbol})")
        
        # 检测间接写入的ASAP备份注释，在其后注入镜像写入
        # 支持多种格式:
        # 1. "; ASAP备份 W024: insert::R12+0" (旧格式)
        # 2. "; ASAP备份 W024: main::SP+0 (间接栈写入)" (新格式)
        # 3. "; ASAP备份 W024: main::SP+0" (简化格式)
        backup_match = re.search(r'; ASAP备份 (W\d+): (\S+)', line)
        if backup_match:
            wid = backup_match.group(1)
            logical_addr = backup_match.group(2)
            
            # 方法1: 检查是否在loop_writes中被标记
            if wid in loop_writes:
                write_info = loop_writes[wid]
                array_name = write_info.get('array_name')
                
                if array_name and array_name in array_mirrors:
                    config = array_mirrors[array_name]
                    # 优先使用config中的param_reg，如果为None则从candidates获取base_reg
                    param_reg = config.get('param_reg')
                    if not param_reg:
                        param_reg = candidates.get(wid, {}).get('base_reg', 'R12')
                    mirror_symbol = config['mirror_symbol']
                    base_symbol = base_slots.get(array_name, {}).get('symbol')
                    
                    # 检查是否是全局数组
                    array_info = loop_arrays.get('arrays', {}).get(array_name, {})
                    is_global = array_info.get('is_global', False)
                    
                    # 获取该WID的offset
                    offset = candidates.get(wid, {}).get('offset', 0)
                    
                    # 根据数组类型生成不同的镜像代码
                    if is_global:
                        # 全局数组使用数组符号名作为基地址，不需要__BASE_xxx
                        mirror_code = generate_global_array_mirror_code(param_reg, mirror_symbol, array_name, wid, offset)
                    elif base_symbol:
                        # 通过参数传递的数组，使用__BASE_xxx
                        mirror_code = generate_mirror_code(param_reg, mirror_symbol, base_symbol, array_name, wid, offset)
                    else:
                        # 无法生成镜像代码（如is_stack_direct但无base_symbol）
                        # 【修复死循环】必须增加i再continue
                        i += 1
                        continue
                    
                    # 找到ASAP备份块的结束位置（WID标签之前）
                    j = i + 1
                    while j < len(lines) and '__WID_' not in lines[j]:
                        output_lines.append(lines[j])
                        j += 1
                    
                    # 在WID标签之前注入镜像代码
                    output_lines.append(mirror_code)
                    
                    # 继续处理WID标签及后续
                    i = j - 1  # 因为外层循环会i++
                    mirror_injected += 1
                    array_type = "全局数组" if is_global else "参数传递"
                    print(f"  注入 {wid}: {array_name} 镜像写入 ({array_type}, 函数: {write_info.get('function')})")
                    continue
            
            # 方法2: 检查是否匹配caller的栈地址（兼容新的INDIRECT_STACK格式）
            for array_name, config in array_mirrors.items():
                param_reg = config.get('param_reg', 'R12')
                caller_func = config.get('caller_func')
                caller_offset = config.get('caller_offset', 0)
                callee_funcs = loop_arrays['arrays'].get(array_name, {}).get('callee_funcs', [])
                
                # 新格式匹配: main::SP+0 (数组在调用者栈上)
                if caller_func and f"{caller_func}::SP+{caller_offset}" == logical_addr:
                    # 确认当前函数是callee
                    if current_func in callee_funcs:
                        mirror_symbol = config['mirror_symbol']
                        base_symbol = base_slots.get(array_name, {}).get('symbol')
                        
                        if base_symbol:
                            # 获取该WID的offset
                            offset = candidates.get(wid, {}).get('offset', 0)
                            mirror_code = generate_mirror_code(param_reg, mirror_symbol, base_symbol, array_name, wid, offset)
                            
                            j = i + 1
                            while j < len(lines) and '__WID_' not in lines[j]:
                                output_lines.append(lines[j])
                                j += 1
                            
                            output_lines.append(mirror_code)
                            i = j - 1
                            mirror_injected += 1
                            print(f"  注入 {wid}: {array_name} 镜像写入 (通过 {logical_addr}, offset={offset})")
                            break
                
                # 旧格式匹配: insert::R12+0
                for callee_func in callee_funcs:
                    if f"{callee_func}::{param_reg}+" in logical_addr:
                        mirror_symbol = config['mirror_symbol']
                        base_symbol = base_slots.get(array_name, {}).get('symbol')
                        
                        if base_symbol:
                            # 获取该WID的offset
                            offset = candidates.get(wid, {}).get('offset', 0)
                            mirror_code = generate_mirror_code(param_reg, mirror_symbol, base_symbol, array_name, wid, offset)
                            
                            j = i + 1
                            while j < len(lines) and '__WID_' not in lines[j]:
                                output_lines.append(lines[j])
                                j += 1
                            
                            output_lines.append(mirror_code)
                            i = j - 1
                            mirror_injected += 1
                            print(f"  注入 {wid}: {array_name} 镜像写入 (旧格式, offset={offset})")
                        break
        
        i += 1
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    print(f"  ✓ 注入了 {mirror_injected} 个镜像写入")
    print(f"  ✓ 输出: {output_file}")


def generate_global_array_mirror_code(param_reg, mirror_symbol, array_name, wid, offset=0):
    """生成全局数组镜像写入的汇编代码
    
    对于全局数组，基地址是固定的（数组符号名），不需要__BASE_xxx
    
    Args:
        param_reg: 当前写入地址寄存器 (如 R12)
        mirror_symbol: FRAM镜像符号
        array_name: 数组名称（也是基地址符号）
        wid: Write ID
        offset: 写入偏移量
    """
    
    # 根据offset确定读取和写入的偏移
    if offset == 0:
        src_operand = f"@{param_reg}"  # 读取 @R12
        dst_operand = "0(R15)"          # 写入 0(R15)
    else:
        src_operand = f"{offset}({param_reg})"  # 读取 2(R12)
        dst_operand = f"{offset}(R15)"          # 写入 2(R15)
    
    code = f"""
\t; ===== {array_name}全局数组镜像写入 ({wid}, offset={offset}) =====
\t; 计算镜像地址: mirror_addr = {mirror_symbol} + ({param_reg} - {array_name}) + {offset}
\tPUSH.W R15\t\t\t; 保存R15
\tMOV.W {param_reg}, R15\t\t; R15 = &{array_name}[index]
\tSUB.W #{array_name}, R15\t; R15 = index * element_size (相对偏移)
\tADD.W #{mirror_symbol}, R15\t; R15 = &{mirror_symbol}[index]
\tMOV.W {src_operand}, {dst_operand}\t; 复制值到镜像 (offset={offset})
\tPOP.W R15\t\t\t; 恢复R15
"""
    return code


def generate_mirror_code(param_reg, mirror_symbol, base_symbol, array_name, wid, offset=0):
    """生成数组镜像写入的汇编代码
    
    Args:
        param_reg: 数组基地址寄存器 (如 R12)
        mirror_symbol: FRAM镜像符号
        base_symbol: 基地址保存符号
        array_name: 数组名称
        wid: Write ID
        offset: 写入偏移量 (如 W099 offset=0 写入@R12, W100 offset=2 写入2(R12))
    """
    
    # 根据offset确定读取和写入的偏移
    if offset == 0:
        src_operand = f"@{param_reg}"  # 读取 @R12
        dst_operand = "0(R15)"          # 写入 0(R15)
    else:
        src_operand = f"{offset}({param_reg})"  # 读取 2(R12)
        dst_operand = f"{offset}(R15)"          # 写入 2(R15)
    
    code = f"""
\t; ===== {array_name}数组镜像写入 ({wid}, offset={offset}) =====
\t; 计算镜像地址: mirror_addr = {mirror_symbol} + ({param_reg} - {base_symbol}) + {offset}
\tPUSH.W R15\t\t\t; 保存R15
\tMOV.W {param_reg}, R15\t\t; R15 = &{array_name}[index]
\tSUB.W &{base_symbol}, R15\t; R15 = index * element_size (相对偏移)
\tADD.W #{mirror_symbol}, R15\t; R15 = &{mirror_symbol}[index]
\tMOV.W {src_operand}, {dst_operand}\t; 复制值到镜像 (offset={offset})
\tPOP.W R15\t\t\t; 恢复R15
"""
    return code


def main():
    parser = argparse.ArgumentParser(description='Stage 5e: 注入数组镜像写入')
    parser.add_argument('--input', default='build/A_instrumented.s', help='输入汇编')
    parser.add_argument('--loop-arrays', default='build/loop_arrays.json', help='循环数组信息')
    parser.add_argument('--fram-slots', default='build/fram_slots.json', help='FRAM槽位')
    parser.add_argument('--candidates', default='build/candidates.json', help='候选写操作JSON（用于获取offset）')
    parser.add_argument('--output', default='build/A_array_mirror.s', help='输出汇编')
    
    args = parser.parse_args()
    
    print("Stage 5e: 注入循环数组镜像写入...")
    
    inject_array_mirror_code(args.input, args.loop_arrays, args.fram_slots, args.output, args.candidates)


if __name__ == '__main__':
    main()

