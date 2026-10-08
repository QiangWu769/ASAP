#!/usr/bin/env python3
"""
Stage 5 Array: 插桩备份逻辑（支持数组索引感知）
输入: build/A_sym.s, build/candidates.json, build/fram_slots.json
输出: build/A_instrumented.s
"""
import argparse
import json
import re

def inject_array_backup(wid, candidate, slot_info, output_lines):
    """
    插入数组索引感知备份（3-4条指令）
    
    假设：
    - 写入后地址在R12中（根据实际汇编）
    - 索引变量位置在 array_info['index_location']
    - 备份数组基址是 __backup_xxx_start（或 __MIRROR_xxx 对于SRAM全局数组）
    """
    array_info = candidate.get('array_info', {})
    index_loc = array_info.get('index_location', '0(R1)')  # 默认假设
    array_base = array_info.get('array_base', 'computed')
    
    # 【CF专用】对于filter等SRAM全局数组，使用__MIRROR_xxx作为备份地址
    # 确保main和insert使用相同的备份位置
    sram_global_arrays = ['filter']  # 【CF专用】filter是SRAM全局数组
    if array_base in sram_global_arrays:
        backup_symbol = f"__MIRROR_{array_base}"
    else:
        backup_symbol = slot_info['slot_symbol']
    
    backup_lines = []
    backup_lines.append(f"\t; === ASAP数组备份 {wid}: 索引感知 ===\n")
    
    # 方案：复用原始计算的地址，然后加偏移到备份区
    # 假设原始地址在R12，使用R14做临时
    backup_lines.append(f"\tMOV.W {index_loc}, R14        ; R14 = i (索引)\n")
    backup_lines.append(f"\tRLAM.W #1, R14                ; R14 = i*2\n")
    backup_lines.append(f"\tADD.W #{backup_symbol}, R14  ; R14 = backup_base + i*2\n")
    backup_lines.append(f"\tMOV.W @R12, @R14              ; backup[i] = array[i]\n")
    
    # 备份SP和WID
    backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    
    wid_num = int(wid[1:])
    backup_lines.append(f"\t.global __WID_{wid}\n")
    backup_lines.append(f"__WID_{wid}:\n")
    backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    output_lines.extend(backup_lines)

def inject_sram_global_backup(wid, candidate, slot_info, output_lines):
    """SRAM全局变量备份（绝对地址）"""
    orig_dst = candidate['dst']  # 如 &0x1C00
    slot_symbol = slot_info['slot_symbol']
    sram_addr = slot_info.get('sram_addr', orig_dst)  # SRAM地址
    
    backup_lines = []
    backup_lines.append(f"\t; ASAP备份 {wid}: SRAM全局变量 {sram_addr}\n")
    backup_lines.append(f"\tMOV.W &{sram_addr}, &{slot_symbol}  ; 备份SRAM值到FRAM\n")
    backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    
    wid_num = int(wid[1:])
    backup_lines.append(f"\t.global __WID_{wid}\n")
    backup_lines.append(f"__WID_{wid}:\n")
    backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    output_lines.extend(backup_lines)

def inject_scalar_backup(wid, candidate, slot_info, output_lines, is_loop_array_write=False):
    """标量备份（原有逻辑）"""
    orig_dst = candidate['dst']
    slot_symbol = slot_info['slot_symbol']
    
    # 【修复】检查原始写入是字节还是字操作
    mnemonic = candidate.get('mnemonic', 'MOV.W')
    is_byte_op = '.B' in mnemonic.upper()
    mov_instr = 'MOV.B' if is_byte_op else 'MOV.W'
    
    backup_lines = []
    
    # 检查是否是间接栈写入
    addr_mode = candidate.get('addr_mode')
    if addr_mode == 'INDIRECT_STACK':
        # 间接栈写入：通过指针访问调用者栈（动态索引）
        # 需要同时保存值和写入地址
        backup_lines.append(f"\t; ASAP备份 {wid}: {slot_info['logical_addr']} (间接栈写入, {mov_instr})\n")
        backup_lines.append(f"\t{mov_instr} {orig_dst}, &{slot_symbol}  ; 备份写入的值\n")
        
        # 【修复】如果是循环数组写入（如crcTable），跳过地址备份
        # 因为全局数组的地址是计算得到的，不是来自调用者栈
        if is_loop_array_write:
            backup_lines.append(f"\t; 跳过地址备份：这是全局数组写入，由镜像机制处理\n")
        else:
            # 额外保存写入地址（从base_reg获取，需要加上offset）
            base_reg = candidate.get('base_reg')
            offset = candidate.get('offset', 0)
            addr_slot_symbol = slot_info.get('addr_slot_symbol')
            if base_reg and addr_slot_symbol:
                if offset == 0:
                    # offset为0时，直接备份寄存器
                    backup_lines.append(f"\tMOV.W {base_reg}, &{addr_slot_symbol}  ; 备份写入地址\n")
                else:
                    # offset不为0时，需要计算实际地址 (base_reg + offset)
                    # 使用R15作为临时寄存器
                    backup_lines.append(f"\tPUSH.W R15  ; 保存R15\n")
                    backup_lines.append(f"\tMOV.W {base_reg}, R15\n")
                    backup_lines.append(f"\tADD.W #{offset}, R15  ; R15 = {base_reg} + {offset}\n")
                    backup_lines.append(f"\tMOV.W R15, &{addr_slot_symbol}  ; 备份实际写入地址({base_reg}+{offset})\n")
                    backup_lines.append(f"\tPOP.W R15  ; 恢复R15\n")
    else:
        # 普通写入
        backup_lines.append(f"\t; ASAP备份 {wid}: {slot_info['logical_addr']} ({mov_instr})\n")
        backup_lines.append(f"\t{mov_instr} {orig_dst}, &{slot_symbol}  ; 备份写入的值\n")
        
        # 普通间接寻址额外备份地址
        # 【修复】如果是全局数组写入，跳过地址备份（由镜像机制处理）
        base_reg = candidate.get('base_reg')
        # 【修复】INDIRECT 或 非SP的INDEXED寻址都需要备份基地址
        needs_addr_backup = (addr_mode == 'INDIRECT' or 
                            (addr_mode == 'INDEXED' and base_reg and base_reg != 'R1'))
        if needs_addr_backup and base_reg and not is_loop_array_write:
            # 使用slot_info中的addr_slot_symbol（如果有的话）
            addr_slot_symbol = slot_info.get('addr_slot_symbol')
            if addr_slot_symbol:
                backup_lines.append(f"\tMOV.W {base_reg}, &{addr_slot_symbol}  ; 备份{base_reg}地址\n")
    
    backup_lines.append(f"\tMOV.W R1, &ASAP_SP_SAVE\n")
    
    wid_num = int(wid[1:])
    backup_lines.append(f"\t.global __WID_{wid}\n")
    backup_lines.append(f"__WID_{wid}:\n")
    backup_lines.append(f"\tMOV.W #{wid_num}, &ASAP_WID_SAVE\n")
    
    output_lines.extend(backup_lines)

def inject_backup(asm_file, candidates, fram_slots, output_file, enable_array_backup=True, loop_arrays_file=None):
    """在每个关键写后插入备份指令（支持数组和SRAM全局变量）"""
    
    # 加载循环数组信息（用于区分全局数组和直接栈数组）
    loop_array_wids = set()
    loop_arrays_data = {}  # 保存完整的loop_arrays数据
    if loop_arrays_file:
        try:
            with open(loop_arrays_file, 'r') as f:
                loop_arrays_data = json.load(f)
                for wid in loop_arrays_data.get('writes', {}).keys():
                    loop_array_wids.add(wid)
        except:
            pass
    
    line_to_wid = {}
    for wid, info in candidates.items():
        line = info['line']
        if line not in line_to_wid:
            line_to_wid[line] = []
        line_to_wid[line].append(wid)
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    output_lines = []
    array_backup_count = 0
    scalar_backup_count = 0
    sram_global_count = 0
    
    for i, line in enumerate(lines, 1):
        if i in line_to_wid:
            wid_list = line_to_wid[i]
            
            # 1. 先输出原始业务代码
            output_lines.append(line)
            
            # 2. 为每个WID生成备份代码
            for wid in wid_list:
                candidate = candidates[wid]
                slot_info = fram_slots['wid_to_slot'][wid]
                
                # === 分支：数组 vs SRAM全局变量 vs 标量 ===
                is_loop_array_write = wid in loop_array_wids
                
                # 【关键修复】检查是否是直接栈数组（is_stack_direct）
                # 直接栈数组需要使用索引感知备份，不能依赖stage5e的镜像机制
                is_stack_direct_array = False
                if is_loop_array_write and loop_arrays_data:
                    write_info = loop_arrays_data.get('writes', {}).get(wid, {})
                    array_name = write_info.get('array_name')
                    if array_name:
                        array_info = loop_arrays_data.get('arrays', {}).get(array_name, {})
                        is_stack_direct_array = array_info.get('is_stack_direct', False)
                
                # 决策逻辑：
                # - 全局数组（is_global）：使用scalar备份，由stage5e处理镜像
                # - 直接栈数组（is_stack_direct）：使用索引感知备份（inject_array_backup）
                # - 其他数组：使用索引感知备份
                if enable_array_backup and candidate.get('type') == 'array':
                    if is_loop_array_write and not is_stack_direct_array:
                        # 全局数组的循环写入，由stage5e处理镜像
                        inject_scalar_backup(wid, candidate, slot_info, output_lines, True)
                        scalar_backup_count += 1
                    else:
                        # 直接栈数组或非循环数组：使用索引感知备份
                        inject_array_backup(wid, candidate, slot_info, output_lines)
                        array_backup_count += 1
                elif candidate.get('addr_mode') == 'SRAM_GLOBAL':
                    inject_sram_global_backup(wid, candidate, slot_info, output_lines)
                    sram_global_count += 1
                else:
                    # 标量备份
                    is_loop_array = wid in loop_array_wids
                    inject_scalar_backup(wid, candidate, slot_info, output_lines, is_loop_array)
                    scalar_backup_count += 1
        else:
            output_lines.append(line)
    
    with open(output_file, 'w') as f:
        f.writelines(output_lines)
    
    return array_backup_count, scalar_backup_count, sram_global_count

def main():
    parser = argparse.ArgumentParser(description='Stage 5 Array: 插桩备份（含数组）')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--candidates', required=True, help='候选写操作JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--output', default='build/A_instrumented.s', help='输出汇编')
    parser.add_argument('--enable-array-backup', action='store_true', help='启用数组索引感知备份')
    parser.add_argument('--loop-arrays', default=None, help='循环数组信息JSON（用于跳过全局数组的INDIRECT_STACK备份）')
    
    args = parser.parse_args()
    
    with open(args.candidates, 'r') as f:
        candidates = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots = json.load(f)
    
    array_count, scalar_count, sram_global_count = inject_backup(
        args.asm_file, candidates, fram_slots, args.output, 
        args.enable_array_backup, args.loop_arrays
    )
    
    print(f"  ✓ 插桩完成:")
    print(f"    - 标量备份: {scalar_count} 个")
    if sram_global_count > 0:
        print(f"    - SRAM全局变量备份: {sram_global_count} 个")
    if args.enable_array_backup:
        print(f"    - 数组备份: {array_count} 个（索引感知）")
    print(f"    - 总计: {len(candidates)} 个关键写")
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

