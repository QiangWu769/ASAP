#!/usr/bin/env python3
"""
Stage 5c: 在函数入口插入返回地址备份
为了支持子函数中断电恢复，需要保存调用栈的返回地址
输入: build/A_instrumented.s, build/function_info.json
输出: build/A_instrumented.s (原地修改)
"""
import argparse
import json
import re

def inject_return_addr_backup(asm_file, function_info, exclude_functions, fram_slots_file=None):
    """在核心函数入口插入返回地址备份"""
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    
    # 从fram_slots.json读取当前FRAM分配位置，避免与数组镜像冲突
    # 默认从0x6500开始（如果没有fram_slots）
    base_addr = 0x6500
    if fram_slots_file:
        try:
            with open(fram_slots_file, 'r') as f:
                fram_slots = json.load(f)
            # 使用next_addr作为起始地址（在所有槽位和镜像之后）
            next_addr = fram_slots.get('next_addr', '0x6500')
            base_addr = int(next_addr, 16) if isinstance(next_addr, str) else next_addr
            print(f"  从fram_slots读取next_addr: 0x{base_addr:04X}")
        except Exception as e:
            print(f"  ⚠ 无法读取fram_slots: {e}，使用默认地址0x6500")
    
    # 为每个核心函数分配SP和返回地址槽位
    func_slots = {}
    sp_slot_addr = base_addr   # 函数SP槽位
    ret_slot_addr = base_addr + 0x20  # 返回地址槽位在SP之后
    
    for func_name, info in function_info.items():
        # 跳过排除的函数
        if func_name.lower() in [f.lower() for f in exclude_functions]:
            continue
        
        # 为每个函数（包括main）分配SP槽位
        func_slots[func_name] = {
            'sp_slot': f'0x{sp_slot_addr:04X}',
            'frame_size': info['stack_size']
        }
        sp_slot_addr += 2
        
        # 只为非main函数分配返回地址槽位
        if func_name != 'main':
            func_slots[func_name]['ret_slot'] = f'0x{ret_slot_addr:04X}'
            ret_slot_addr += 2
    
    if not func_slots:
        print("  ⚠ 没有需要保存SP/返回地址的函数")
        return False
    
    injected_count = 0
    injected_functions = set()  # 防止重复注入
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 检测函数标签
        func_match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*):', line)
        if func_match:
            func_name = func_match.group(1)
            
            # 如果是需要保存SP/返回地址的函数，且未注入过
            if func_name in func_slots and func_name not in injected_functions:
                output_lines.append(line)  # 添加函数标签
                
                slot_info = func_slots[func_name]
                frame_size = slot_info['frame_size']
                sp_slot = slot_info['sp_slot']
                ret_slot = slot_info.get('ret_slot')  # main没有返回地址
                
                # 跳过标签和空行，找到prologue指令
                j = i + 1
                while j < len(lines) and j < i + 15:
                    stripped = lines[j].strip()
                    # 跳过空行、注释、.L标签
                    if not stripped or stripped.startswith(';') or stripped.startswith('.'):
                        output_lines.append(lines[j])
                        j += 1
                        continue
                    # 找到第一条真正的指令（prologue）
                    break
                
                # 添加prologue指令
                prologue_count = 0
                while j < len(lines) and prologue_count < 3:
                    stripped = lines[j].strip()
                    if stripped and not stripped.startswith(';') and not stripped.startswith('.'):
                        # 检查是否是prologue指令
                        if re.search(r'\b(PUSHM|PUSH|SUB.*R1)\b', stripped, re.IGNORECASE):
                            output_lines.append(lines[j])
                            prologue_count += 1
                            j += 1
                        else:
                            break
                    else:
                        output_lines.append(lines[j])
                        j += 1
                
                # 【修改】只在非main函数保存返回地址（不再保存SP）
                # SP在恢复时通过ASAP_SP_SAVE + 栈帧偏移计算
                backup_code = []
                
                if ret_slot:
                    # 只保存返回地址（main不需要）
                    # 直接备份，不使用中间寄存器，避免栈偏移问题
                    # sub #frame_size, r1 后，返回地址在 frame_size(r1)
                    ret_offset = frame_size
                    backup_code.extend([
                        f'\t; ===== 保存返回地址（用于调用栈重建）=====\n',
                        f'\tMOV.W\t{ret_offset}(R1), &{ret_slot}\t; 直接备份返回地址到FRAM\n',
                        '\n'
                    ])
                
                if backup_code:  # 只在有返回地址时才插入
                    output_lines.extend(backup_code)
                
                injected_count += 1
                injected_functions.add(func_name)
                
                # 继续从j开始处理
                i = j
                continue
        
        output_lines.append(line)
        i += 1
    
    # 写回文件
    with open(asm_file, 'w') as f:
        f.writelines(output_lines)
    
    # 生成汇编符号文件（定义返回地址符号为全局符号）
    symbol_asm_file = asm_file.replace('A_instrumented.s', 'func_sp_symbols.s')
    with open(symbol_asm_file, 'w') as f:
        f.write('; 函数返回地址FRAM槽位符号（用于调用栈重建）\n')
        f.write('    .section .text\n')
        for func_name, info in func_slots.items():
            # 只输出返回地址槽位符号（如果有）
            if 'ret_slot' in info:
                ret_symbol = f'RET_ADDR_{func_name.upper()}'
                f.write(f'    .global {ret_symbol}\n')
                f.write(f'    .equ {ret_symbol}, {info["ret_slot"]}\n')
    
    # 也生成.ld文件（用于向后兼容，但主要使用.s文件）
    linker_file = asm_file.replace('A_instrumented.s', 'func_sp_symbols.ld')
    with open(linker_file, 'w') as f:
        f.write('/* 函数返回地址FRAM槽位符号（SP不再保存，恢复时计算）*/\n')
        for func_name, info in func_slots.items():
            if 'ret_slot' in info:
                ret_symbol = f'RET_ADDR_{func_name.upper()}'
                f.write(f'{ret_symbol} = {info["ret_slot"]};\n')
    
    return injected_count, func_slots

def main():
    parser = argparse.ArgumentParser(description='在函数入口插入返回地址备份')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--exclude', nargs='*', default=[], help='排除的函数列表')
    parser.add_argument('--config', help='配置文件JSON（可选，用于读取exclude_functions）')
    parser.add_argument('--fram-slots', help='FRAM槽位分配JSON（用于确定返回地址槽位起始地址）')
    
    args = parser.parse_args()
    
    # 加载函数信息
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    # 默认排除初始化函数（UART业务函数已从默认排除中移除）
    default_exclude = ['INIT_CONSOLE', 'clock_init', 'uart_init', 'init_hw']
    
    # 从配置文件读取exclude列表（如果提供）
    config_exclude = []
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
                config_exclude = config.get('exclude_functions', [])
                print(f"  从配置文件读取到 {len(config_exclude)} 个排除函数")
        except Exception as e:
            print(f"  ⚠ 警告：无法读取配置文件 {args.config}: {e}")
    
    exclude_functions = list(set(default_exclude + args.exclude + config_exclude))
    
    # 传递fram_slots文件以获取正确的起始地址
    fram_slots_file = getattr(args, 'fram_slots', None)
    result = inject_return_addr_backup(args.asm_file, function_info, exclude_functions, fram_slots_file)
    
    if result:
        injected_count, func_slots = result
        ret_count = sum(1 for info in func_slots.values() if 'ret_slot' in info)
        print(f"  ✓ 已为 {ret_count} 个子函数插入返回地址备份（SP改用编译时计算）")
        for func_name in sorted(func_slots.keys()):
            info = func_slots[func_name]
            if 'ret_slot' in info:
                print(f"    {func_name}: ret={info['ret_slot']}")
    else:
        print(f"  ⚠ 未插入返回地址备份")
    
    print(f"  ✓ 输出: {args.asm_file}")

if __name__ == '__main__':
    main()

