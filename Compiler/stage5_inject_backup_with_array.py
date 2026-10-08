#!/usr/bin/env python3
"""
Stage 5: 插桩备份逻辑 + 动态数组哈希表备份
在每个关键写后插入备份指令
+ 在每个函数入口备份参数寄存器R12-R15
输入: build/A_sym.s, build/candidates.json, build/fram_slots.json
输出: build/A_instrumented.s

【新增功能】为动态数组WID生成哈希表备份代码
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


# ============================================================
# 【新增功能】动态数组哈希表备份代码生成
# ============================================================

def generate_array_backup_code(wid, wid_info, slot_info):
    """
    生成动态数组的哈希表备份代码
    
    参数:
        wid: WID编号，如 "W024"
        wid_info: candidates中的WID信息
        slot_info: fram_slots中的槽位信息（包含哈希表地址）
    
    返回:
        备份代码行列表
    """
    
    backup_lines = []
    wid_num = int(wid[1:])
    
    backup_lines.append(f"\t; ASAP动态数组备份 {wid}: {slot_info['logical_addr']}\n")
    
    # 准备参数:
    #   R13 = target_addr (写入的实际地址，即@R12的值)
    #   R14 = value (要备份的值)
    #   R15 = hashtable_addr (哈希表地址)
    
    base_reg = wid_info.get('base_reg', 'R12')
    
    # R13 = 目标地址（base_reg的值）
    backup_lines.append(f"\tMOV.W {base_reg}, R13\t; R13 = target_addr\n")
    
    # R14 = 写入的值
    backup_lines.append(f"\tMOV.W @{base_reg}, R14\t; R14 = value\n")
    
    # R15 = 哈希表基址
    hashtable_symbol = slot_info['hashtable_symbol']
    backup_lines.append(f"\tMOV.W #{hashtable_symbol}, R15\t; R15 = hashtable_addr\n")
    
    # 调用运行时哈希表插入函数
    backup_lines.append(f"\tCALL #__asap_hashtable_insert\n")
    
    # 【常规】备份WID和SP
    backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    backup_lines.append(f"\t.global __WID_{wid}\n")
    backup_lines.append(f"__WID_{wid}:\n")
    backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    return backup_lines


def generate_regular_backup_code(wid, wid_info, slot_info, line):
    """
    【原有逻辑】生成常规备份代码
    
    参数:
        wid: WID编号
        wid_info: candidates中的WID信息
        slot_info: fram_slots中的槽位信息
        line: 原始指令行
    
    返回:
        备份代码行列表
    """
    
    wid_num = int(wid[1:])
    orig_dst = wid_info['dst']
    slot_symbol = slot_info['slot_symbol']
    
    backup_lines = []
    backup_lines.append(f"\t; ASAP备份 {wid}: {slot_info['logical_addr']}\n")
    
    # 2.1 备份变量值到FRAM
    backup_lines.append(f"\tMOV.W {orig_dst}, &{slot_symbol}\n")
    
    # 2.1.5 【新增】如果是间接寻址，额外备份寄存器地址
    addr_mode = wid_info.get('addr_mode')
    base_reg = wid_info.get('base_reg')
    if addr_mode == 'INDIRECT' and base_reg:
        # 为间接寻址分配专用的地址槽位
        addr_slot_symbol = slot_info.get('addr_slot_symbol')
        if addr_slot_symbol:
            backup_lines.append(f"\tMOV.W {base_reg}, &{addr_slot_symbol}  ; 备份{base_reg}地址\n")
    
    # 2.2 备份SP
    backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    
    # 2.2.5 【禁用】寄存器备份（导致严重问题）
    # used_regs = detect_used_registers(line)
    # 不再备份寄存器
    
    # 2.3 ⭐ WID标签和保存（放在最后！）
    backup_lines.append(f"\t.global __WID_{wid}\n")
    backup_lines.append(f"__WID_{wid}:\n")
    backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    return backup_lines


# ============================================================
# 主插桩逻辑（增强版）
# ============================================================

def inject_backup(asm_file, candidates, fram_slots, output_file, enable_power_sim=False, fail_at_wid=None):
    """在每个关键写后插入备份指令（支持动态数组）"""
    
    # 构建行号→WID列表映射（支持同一行多个WID）
    line_to_wid = {}
    for wid, info in candidates.items():
        line = info['line']
        if line not in line_to_wid:
            line_to_wid[line] = []
        line_to_wid[line].append(wid)
    
    # 记录每个WID备份的寄存器
    wid_backup_regs = {}
    
    # 统计
    regular_count = 0
    array_count = 0
    
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
                wid_info = candidates[wid]
                
                # 【新增】判断是否是动态数组
                if slot_info.get('is_dynamic_array', False):
                    # 生成动态数组哈希表备份代码
                    backup_lines = generate_array_backup_code(wid, wid_info, slot_info)
                    array_count += 1
                else:
                    # 【原有逻辑】生成常规备份代码
                    backup_lines = generate_regular_backup_code(wid, wid_info, slot_info, line)
                    regular_count += 1
                
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
                
                # 记录寄存器备份（这里不再使用）
                wid_backup_regs[wid] = []
        else:
            # 非关键写的行，直接输出
            output_lines.append(line)
    
    # 写入输出文件
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    # 返回统计信息
    return {
        'wid_backup_regs': wid_backup_regs,
        'regular_count': regular_count,
        'array_count': array_count
    }


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Stage 5: 插桩备份 + 动态数组哈希表')
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
    
    # 直接插桩WID备份（支持动态数组）
    result = inject_backup(args.asm_file, candidates, fram_slots, args.output, 
                          args.enable_power_sim, args.fail_at_wid)
    
    # 保存寄存器备份元数据
    with open('build/wid_backup_regs.json', 'w') as f:
        json.dump(result['wid_backup_regs'], f, indent=2)
    
    # 统计报告
    total_wids = len(candidates)
    regular_count = result['regular_count']
    array_count = result['array_count']
    
    print(f"  ✓ 插桩完成:")
    print(f"    - 处理了 {total_wids} 个关键写")
    print(f"      · 常规备份: {regular_count} 个")
    print(f"      · 动态数组哈希表备份: {array_count} 个")
    print(f"    - 插桩顺序：业务代码 → 备份 → WID标签")
    
    if args.enable_power_sim and args.fail_at_wid:
        print(f"    - ⚡ 断电模拟: 在 {args.fail_at_wid} 后触发")
    
    print(f"  ✓ 输出: {args.output}")
    print(f"  ✓ 寄存器元数据: build/wid_backup_regs.json")

if __name__ == '__main__':
    main()


