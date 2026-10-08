#!/usr/bin/env python3
"""
Stage 5f: 备份下一条写入要用的寄存器

问题：WID N设置后紧跟WID N+1的原始写入。如果N+1的写入使用寄存器(如MOV R13, @R1)，
      恢复WID N后会用垃圾寄存器值覆盖刚恢复的栈。

解决：在WID设置之前，备份下一条写入要用的寄存器到FRAM。恢复时先恢复寄存器。
"""
import argparse
import re
import json
import os

def analyze_and_inject(asm_path, output_path, fram_slots_path, fram_symbols_path):
    """分析汇编代码，在需要的地方注入寄存器备份"""
    
    with open(asm_path, 'r') as f:
        lines = f.readlines()
    
    # 第一遍：找出所有WID和其后的寄存器写入
    wid_next_reg = {}  # {wid_num: (reg, line_index)}
    
    for i, line in enumerate(lines):
        # 匹配WID标签
        wid_match = re.match(r'^__WID_(W\d+):', line.strip())
        if wid_match:
            wid = wid_match.group(1)
            wid_num = int(wid[1:])
            
            # 往后找紧跟的原始写入指令
            for j in range(i+1, min(i+10, len(lines))):
                next_line = lines[j].strip()
                
                # 跳过WID设置指令和空行/注释
                if 'ASAP_WID_SAVE' in next_line or not next_line or next_line.startswith(';'):
                    continue
                if next_line.startswith('.loc') or next_line.startswith('.global'):
                    continue
                
                # 检查是否是使用寄存器写入栈的指令
                reg_write = re.match(r'MOV\.W\s+R(\d+),\s*(?:@R1|\d+\(R1\))', next_line, re.IGNORECASE)
                if reg_write:
                    reg_num = int(reg_write.group(1))
                    wid_next_reg[wid_num] = (f'R{reg_num}', j)
                    print(f"  [分析] WID {wid}: 后续写入使用 R{reg_num}")
                    break
                
                # 【新增】检查是否是通过寄存器间接读取的指令
                # 如 MOV.B @R12, R12 或 MOV.W @R13, R14
                reg_indirect_read = re.match(r'MOV\.[BW]\s+@R(\d+),\s*R\d+', next_line, re.IGNORECASE)
                if reg_indirect_read:
                    reg_num = int(reg_indirect_read.group(1))
                    # 跳过 R1 (SP)，它由 ASAP_SP_SAVE 处理
                    if reg_num != 1:
                        wid_next_reg[wid_num] = (f'R{reg_num}', j)
                        print(f"  [分析] WID {wid}: 后续间接读取使用 R{reg_num}")
                        break
                
                # 【新增】检查是否是通过寄存器索引读取的指令
                # 如 MOV.W 0(R12), R14
                reg_indexed_read = re.match(r'MOV\.[BW]\s+\d+\(R(\d+)\),\s*R\d+', next_line, re.IGNORECASE)
                if reg_indexed_read:
                    reg_num = int(reg_indexed_read.group(1))
                    if reg_num != 1:
                        wid_next_reg[wid_num] = (f'R{reg_num}', j)
                        print(f"  [分析] WID {wid}: 后续索引读取使用 R{reg_num}")
                        break
                
                # 【修复】检查是否是使用寄存器作为源和目标的算术指令
                # 如 ADD.B #48, R13 或 ADD.W #1, R12 或 SUB.W #1, R14
                # 这类指令需要寄存器的当前值
                reg_arith = re.match(r'(ADD|SUB)\.[BW]\s+#[^,]+,\s*R(\d+)', next_line, re.IGNORECASE)
                if reg_arith:
                    reg_num = int(reg_arith.group(2))
                    if reg_num != 1:  # 跳过 R1 (SP)
                        wid_next_reg[wid_num] = (f'R{reg_num}', j)
                        print(f"  [分析] WID {wid}: 后续算术运算使用 R{reg_num}")
                        break
                
                # 【修复】检查是否是使用寄存器间接写入的指令
                # 如 MOV.B @R12, 1(R13) - 需要 R12 作为源地址
                reg_indirect_src = re.match(r'MOV\.[BW]\s+@R(\d+),\s*\d*\(R\d+\)', next_line, re.IGNORECASE)
                if reg_indirect_src:
                    reg_num = int(reg_indirect_src.group(1))
                    if reg_num != 1:
                        wid_next_reg[wid_num] = (f'R{reg_num}', j)
                        print(f"  [分析] WID {wid}: 后续间接源使用 R{reg_num}")
                        break
                
                break  # 只检查紧跟的一条指令
    
    print(f"  [分析] 共 {len(wid_next_reg)} 个WID需要备份寄存器")
    
    if not wid_next_reg:
        print("  [跳过] 没有需要备份的寄存器")
        with open(output_path, 'w') as f:
            f.writelines(lines)
        return {}
    
    # 生成需要的寄存器槽位
    regs_needed = set(reg for reg, _ in wid_next_reg.values())
    print(f"  [分析] 需要备份的寄存器: {regs_needed}")
    
    # 读取现有FRAM槽位分配
    with open(fram_slots_path, 'r') as f:
        fram_slots = json.load(f)
    
    # 找最大地址
    max_addr = 0
    for k, v in fram_slots.items():
        if isinstance(v, str) and v.startswith('0x'):
            addr = int(v, 16)
            if addr > max_addr:
                max_addr = addr
    
    # 为寄存器分配FRAM槽位
    reg_slots = {}  # {reg: slot_symbol}
    reg_addrs = {}  # {reg: address}
    next_addr = max_addr + 2
    
    for reg in sorted(regs_needed):
        slot = f'__SLOT_REG_{reg}'
        reg_slots[reg] = slot
        reg_addrs[reg] = f'0x{next_addr:04X}'
        fram_slots[slot] = f'0x{next_addr:04X}'
        print(f"  [分配] {slot} = 0x{next_addr:04X}")
        next_addr += 2
    
    # 保存更新后的FRAM槽位
    with open(fram_slots_path, 'w') as f:
        json.dump(fram_slots, f, indent=2)
    
    # 更新fram_symbols.ld
    with open(fram_symbols_path, 'a') as f:
        f.write('\n/* ===== 寄存器备份槽位 (stage5f) ===== */\n')
        for reg in sorted(regs_needed):
            slot = reg_slots[reg]
            addr = reg_addrs[reg]
            f.write(f'{slot} = {addr};\n')
    
    # 第二遍：在每个WID标签前注入寄存器备份
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 检查是否是WID标签
        wid_match = re.match(r'^__WID_(W\d+):', line.strip())
        if wid_match:
            wid = wid_match.group(1)
            wid_num = int(wid[1:])
            
            if wid_num in wid_next_reg:
                reg, _ = wid_next_reg[wid_num]
                slot = reg_slots[reg]
                
                # 在WID标签前插入寄存器备份（在.global之前）
                if i > 0 and '.global __WID_' in lines[i-1]:
                    # 已经输出了.global，需要在它之前插入
                    backup_line = f'\tMOV.W {reg}, &{slot}  ; 备份{reg}供恢复后使用\n'
                    for k in range(len(new_lines)-1, -1, -1):
                        if '.global __WID_' in new_lines[k]:
                            new_lines.insert(k, backup_line)
                            print(f"  [注入] WID {wid}: 备份 {reg} → {slot}")
                            break
                else:
                    backup_line = f'\tMOV.W {reg}, &{slot}  ; 备份{reg}供恢复后使用\n'
                    new_lines.append(backup_line)
                    print(f"  [注入] WID {wid}: 备份 {reg} → {slot}")
        
        new_lines.append(line)
        i += 1
    
    # 在文件开头添加寄存器槽位声明
    header_lines = []
    for reg in sorted(regs_needed):
        slot = reg_slots[reg]
        header_lines.append(f'\t.extern {slot}\n')
    
    # 找到第一个.section .text的位置
    for i, line in enumerate(new_lines):
        if '.section' in line and '.text' in line:
            new_lines = new_lines[:i] + header_lines + new_lines[i:]
            break
    
    with open(output_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"  ✓ 输出: {output_path}")
    
    # 返回WID到寄存器的映射（供恢复脚本使用）
    return {wid_num: reg for wid_num, (reg, _) in wid_next_reg.items()}

def main():
    parser = argparse.ArgumentParser(description='Stage 5f: 备份下一条写入的寄存器')
    parser.add_argument('--input', required=True, help='输入汇编文件')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON文件')
    parser.add_argument('--fram-symbols', required=True, help='FRAM符号LD文件')
    parser.add_argument('--reg-map', default='build/wid_reg_map.json', help='WID→寄存器映射输出')
    
    args = parser.parse_args()
    
    print("Stage 5f: 备份下一条写入的寄存器...")
    wid_reg_map = analyze_and_inject(args.input, args.output, args.fram_slots, args.fram_symbols)
    
    # 保存映射供恢复脚本使用
    with open(args.reg_map, 'w') as f:
        json.dump(wid_reg_map, f, indent=2)
    print(f"  ✓ 寄存器映射: {args.reg_map}")

if __name__ == '__main__':
    main()

