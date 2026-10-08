#!/usr/bin/env python3
"""
Stage 5: 插桩备份逻辑
在每个关键写后插入备份指令
+ 在每个函数入口备份参数寄存器R12-R15
输入: build/A_sym.s, build/candidates.json, build/fram_slots.json
输出: build/A_instrumented.s
"""
import argparse
import json
import re

def detect_used_registers(instruction):
    """检测指令中使用的R12-R15寄存器"""
    used_regs = set()
    # 匹配 R12-R15（不区分大小写）
    for match in re.finditer(r'\bR1([2-5])\b', instruction, re.IGNORECASE):
        reg_num = int(match.group(1))
        used_regs.add(f'R1{reg_num}')
    return used_regs

def inject_function_entry_backup(asm_file, output_file):
    """在每个函数入口（prologue之后）备份R12-R15
    
    排除main和init相关函数，因为它们在冷启动时R12-R15是未初始化的
    """
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 需要排除的函数（冷启动入口，寄存器未初始化）
    exclude_funcs = ['main', 'init', '__init', '_init']
    
    output_lines = []
    i = 0
    func_count = 0
    current_func = None
    
    while i < len(lines):
        line = lines[i]
        
        # 检测函数标签
        func_match = re.match(r'^([a-zA-Z_][\w]*):$', line)
        if func_match:
            current_func = func_match.group(1)
        
        output_lines.append(line)
        
        # 检测函数 prologue 结束标记: "; end of prologue"
        if '; end of prologue' in line and current_func:
            # 检查是否需要排除
            should_skip = any(current_func.lower().startswith(ef.lower()) for ef in exclude_funcs)
            
            if not should_skip:
                func_count += 1
                # 插入寄存器备份
                output_lines.append('\t; === ASAP: 备份参数寄存器（函数入口） ===\n')
                output_lines.append('\tMOV.W R12, &0x65E0\n')
                output_lines.append('\tMOV.W R13, &0x65E2\n')
                output_lines.append('\tMOV.W R14, &0x65E4\n')
                output_lines.append('\tMOV.W R15, &0x65E6\n')
        
        i += 1
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    return func_count

def inject_backup(asm_file, candidates, fram_slots, output_file, enable_power_sim=False, fail_at_wid=None):
    """在每个关键写后插入备份指令"""
    
    # 构建行号→WID列表映射（支持同一行多个WID）
    line_to_wid = {}
    for wid, info in candidates.items():
        line = info['line']
        if line not in line_to_wid:
            line_to_wid[line] = []
        line_to_wid[line].append(wid)
    
    # 记录每个WID备份的寄存器
    wid_backup_regs = {}
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    wid_counter = 0
    
    for i, line in enumerate(lines, 1):
        # 检查是否是关键写（可能有多个WID）
        if i in line_to_wid:
            wid_list = line_to_wid[i]
            
            # ⭐ 修复顺序：1.业务代码 → 2.备份 → 3.WID标签
            # 1. 先输出原始业务代码（关键写）
            output_lines.append(line)
            
            # 2. 为每个WID生成备份代码
            for wid in wid_list:
                wid_counter += 1
                slot_info = fram_slots['wid_to_slot'][wid]
                orig_dst = candidates[wid]['dst']
                slot_symbol = slot_info['slot_symbol']
                
                backup_lines = []
                backup_lines.append(f"\t; ASAP备份 {wid}: {slot_info['logical_addr']}\n")
                
                # 2.1 备份变量值到FRAM
                backup_lines.append(f"\tMOV.W {orig_dst}, &{slot_symbol}\n")
                
                # 2.1.5 【新增】如果是间接寻址，额外备份寄存器地址
                addr_mode = candidates[wid].get('addr_mode')
                base_reg = candidates[wid].get('base_reg')
                offset = candidates[wid].get('offset', 0)
                
                if addr_mode == 'INDIRECT' and base_reg:
                    # 为间接寻址分配专用的地址槽位
                    addr_slot_symbol = f"__ADDR_{slot_info['logical_addr'].replace('::', '_').replace('+', '_')}"
                    backup_lines.append(f"\tMOV.W {base_reg}, &{addr_slot_symbol}  ; 备份{base_reg}地址\n")
                
                elif addr_mode == 'INDIRECT_STACK' and base_reg:
                    # 间接栈写入：备份实际写入地址（base_reg + offset）
                    addr_slot_symbol = f"__ADDR_{slot_info['logical_addr'].replace('::', '_').replace('+', '_')}"
                    if offset == 0:
                        # offset为0时，直接备份寄存器
                        backup_lines.append(f"\tMOV.W {base_reg}, &{addr_slot_symbol}  ; 备份{base_reg}地址\n")
                    else:
                        # offset不为0时，需要计算实际地址 (base_reg + offset)
                        # 使用R15作为临时寄存器
                        backup_lines.append(f"\tPUSH.W R15  ; 保存R15\n")
                        backup_lines.append(f"\tMOV.W {base_reg}, R15\n")
                        backup_lines.append(f"\tADD.W #{offset}, R15  ; R15 = {base_reg} + {offset}\n")
                        backup_lines.append(f"\tMOV.W R15, &{addr_slot_symbol}  ; 备份实际写入地址\n")
                        backup_lines.append(f"\tPOP.W R15  ; 恢复R15\n")
                
                # 2.2 备份SP
                backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
                
                # 2.2.5 【禁用】寄存器备份（导致严重问题）
                used_regs = detect_used_registers(line)
                wid_backup_regs[wid] = []  # 不再备份寄存器
                # if used_regs:
                #     backup_lines.append(f"\t; 备份参数寄存器: {', '.join(sorted(used_regs))}\n")
                #     reg_to_addr = {'R12': '0x65E0', 'R13': '0x65E2', 'R14': '0x65E4', 'R15': '0x65E6'}
                #     for reg in sorted(used_regs):
                #         backup_lines.append(f"\tMOV.W {reg}, &{reg_to_addr[reg]}\n")
                
                # 2.3 ⭐ WID标签和保存（放在最后！）
                wid_num = int(wid[1:])  # W002 -> 2
                backup_lines.append(f"\t.global __WID_{wid}\n")
                backup_lines.append(f"__WID_{wid}:\n")
                backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
                
                # 2.4 断电模拟（如果启用）
                if enable_power_sim and fail_at_wid == wid:
                    backup_lines.append(f"\t; === 断电模拟：在{wid}后触发 ===\n")
                    backup_lines.append(f"\t; 确保FRAM写入完成\n")
                    backup_lines.append(f"\tNOP\n")
                    backup_lines.append(f"\tNOP\n")
                    backup_lines.append(f"\tNOP\n")
                    backup_lines.append(f"\tNOP\n")
                    backup_lines.append(f"\tMOV.W #0x6904, &0x0120\t; PMMCTL0 = PMMPW | PMMSWPOR (触发软件POR)\n")
                    backup_lines.append(f"__power_fail_loop:\n")
                    backup_lines.append(f"\tJMP __power_fail_loop\t; 等待复位\n")
                
                # ⭐ 恢复点 = WID地址 + 6（stage7自动提取）
                # 跳过已完成的业务代码和备份，保证幂等性
                
                output_lines.extend(backup_lines)
        else:
            # 非关键写的行，直接输出
            output_lines.append(line)
    
    # 写入输出文件
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    # 保存WID寄存器备份元数据
    return wid_backup_regs

def main():
    parser = argparse.ArgumentParser(description='Stage 5: 插桩备份')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--output', default='build/A_instrumented.s', help='输出汇编')
    parser.add_argument('--enable-power-sim', action='store_true', help='启用断电模拟')
    parser.add_argument('--fail-at-wid', default=None, help='在指定WID后触发断电（如W010）')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    # 【禁用】函数入口寄存器备份（导致输出乱码）
    # temp_file = 'build/A_func_backup.s'
    # func_count = inject_function_entry_backup(args.asm_file, temp_file)
    # print(f"  ✓ 函数入口寄存器备份: 处理了 {func_count} 个函数")
    
    # 直接插桩WID备份（不备份寄存器）
    wid_backup_regs = inject_backup(args.asm_file, candidates, fram_slots, args.output, 
                                     args.enable_power_sim, args.fail_at_wid)
    
    # 保存寄存器备份元数据
    with open('build/wid_backup_regs.json', 'w') as f:
        json.dump(wid_backup_regs, f, indent=2)
    
    # 统计寄存器备份
    with_regs = sum(1 for regs in wid_backup_regs.values() if regs)
    without_regs = len(wid_backup_regs) - with_regs
    
    print(f"  ✓ 插桩完成:")
    print(f"    - 处理了 {len(candidates)} 个关键写")
    print(f"    - 插桩顺序：业务代码 → 备份 → 寄存器备份 → WID标签")
    print(f"    - 寄存器备份: {with_regs} 个WID用到R12-R15, {without_regs} 个未使用")
    if args.enable_power_sim and args.fail_at_wid:
        print(f"    - ⚡ 断电模拟: 在 {args.fail_at_wid} 后触发")
    print(f"  ✓ 输出: {args.output}")
    print(f"  ✓ 寄存器元数据: build/wid_backup_regs.json")

if __name__ == '__main__':
    main()

