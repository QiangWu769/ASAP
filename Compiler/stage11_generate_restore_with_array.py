#!/usr/bin/env python3
"""
Stage 11: 生成恢复逻辑（表驱动 + 去重优化 + 动态数组支持）

【新增功能】
- 支持动态数组哈希表恢复
- 恢复表中使用0xFFF0标记动态数组项
- 调用__asap_hashtable_restore函数恢复数组元素

输入: build/pc_ranges.json, build/fram_slots.json
输出: build/asap_restore.s
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

def restore_list_to_tuple(restore_list):
    """将恢复列表转换为可哈希的元组，用于去重"""
    items = []
    for item in restore_list:
        # 【新增】考虑is_dynamic_array标记
        logical_addr = item.get('logical_addr', '')
        slot_addr = item.get('slot_addr', '')
        redirect_target = item.get('redirect_target', '')
        is_dyn_array = item.get('is_dynamic_array', False)
        items.append((logical_addr, slot_addr, redirect_target, is_dyn_array))
    return tuple(items)

def load_pc_ranges_with_array_info(pc_ranges_file, fram_slots_file):
    """
    加载pc_ranges并添加动态数组信息
    
    【新增】为动态数组WID在恢复列表开头插入哈希表恢复项
    """
    with open(pc_ranges_file, 'r') as f:
        pc_ranges_data = json.load(f)
    
    with open(fram_slots_file, 'r') as f:
        fram_slots = json.load(f)
    
    # 为每个WID检查是否是动态数组
    ranges = pc_ranges_data.get('ranges', [])
    for wid_data in ranges:
        wid = wid_data['wid']
        wid_slot_info = fram_slots.get('wid_to_slot', {}).get(wid, {})
        
        # 【关键修复】如果WID本身是动态数组，在恢复列表开头插入哈希表项
        if wid_slot_info.get('is_dynamic_array', False):
            restore_list = wid_data.get('restore_list', [])
            
            # 创建动态数组恢复项
            array_item = {
                'logical_addr': wid_slot_info['logical_addr'],
                'is_dynamic_array': True,
                'hashtable_symbol': wid_slot_info['hashtable_symbol'],
                'size_symbol': wid_slot_info['size_symbol'],
                'slot_symbol': wid_slot_info['hashtable_symbol']  # 用于去重
            }
            
            # 插入到恢复列表开头
            restore_list.insert(0, array_item)
            wid_data['restore_list'] = restore_list
    
    return pc_ranges_data, fram_slots


def generate_restore_asm_with_array(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, wid_backup_regs, output_path):
    """生成汇编格式的恢复逻辑（支持动态数组）"""
    
    ranges = pc_ranges_data.get('ranges', [])
    
    # ======= 第一步：识别唯一的恢复列表 =======
    print("  [去重] 分析恢复列表相似性（包含动态数组）...")
    unique_lists = {}  
    wid_to_list_id = {}  
    
    for wid_data in ranges:
        wid = wid_data['wid']
        restore_list = wid_data.get('restore_list', [])
        restore_tuple = restore_list_to_tuple(restore_list)
        
        if restore_tuple not in unique_lists:
            list_id = len(unique_lists) + 1
            unique_lists[restore_tuple] = {
                'id': list_id,
                'wids': [],
                'restore_list': restore_list,
                'call_stack': wid_data.get('call_stack', []),
                'wid_function': None
            }
            if restore_list:
                first_addr = restore_list[0]['logical_addr']
                if '::SP+' in first_addr:
                    unique_lists[restore_tuple]['wid_function'] = first_addr.split('::')[0]
        
        unique_lists[restore_tuple]['wids'].append(wid)
        wid_to_list_id[wid] = unique_lists[restore_tuple]['id']
    
    print(f"  [去重] 找到 {len(ranges)} 个 WID, {len(unique_lists)} 个唯一恢复列表")
    print(f"  [去重] 去重率: {(1 - len(unique_lists) / len(ranges)) * 100:.1f}%")
    
    # ======= 第二步：生成汇编代码 =======
    with open(output_path, 'w') as f:
        # 文件头
        f.write('; ================================================\n')
        f.write('; ASAP 恢复逻辑 - 支持动态数组哈希表\n')
        f.write('; 自动生成 - 请勿手动编辑\n')
        f.write(f'; 总 WID: {len(ranges)}, 唯一恢复列表: {len(unique_lists)}\n')
        f.write('; ================================================\n\n')
        
        # 声明外部符号
        f.write('    .global _asap_restore\n')
        f.write('    .global __asap_restored_flag\n')
        f.write('    .extern ASAP_WID_SAVE\n')
        f.write('    .extern ASAP_SP_SAVE\n')
        f.write('    .extern ASAP_PC_SAVE\n')
        f.write('    .extern __asap_hashtable_restore  ; 动态数组恢复函数\n\n')
        
        # 在SRAM BSS段定义恢复标志
        f.write('    .section .bss\n')
        f.write('__asap_restored_flag:\n')
        f.write('    .word 0  ; 恢复标志（SRAM中）\n\n')
        
        # 恢复表数据段
        f.write('    .section .rodata\n')
        f.write('    .align 2\n\n')
        
        # ======= 生成唯一的恢复列表 =======
        f.write('; 唯一恢复列表（含动态数组）\n')
        
        for restore_tuple, info in sorted(unique_lists.items(), key=lambda x: x[1]['id']):
            list_id = info['id']
            restore_list = info['restore_list']
            wid_function = info['wid_function']
            call_stack = info['call_stack']
            
            f.write(f'; 恢复列表 #{list_id}: {len(restore_list)} 项, 被 {len(info["wids"])} 个 WID 共享\n')
            f.write(f'_unique_restore_list_{list_id}:\n')
            
            # 预计算SP调整量
            func_sp_adjustments = {}
            current_adjustment = 0
            
            if not call_stack and wid_function:
                call_stack = [wid_function]
            
            for i in range(len(call_stack) - 1, -1, -1):
                func_name = call_stack[i]
                func_sp_adjustments[func_name] = current_adjustment
                if i > 0:
                    frame_size = function_info.get(func_name, {}).get('stack_size', 0)
                    current_adjustment += frame_size + 2
            
            # 生成恢复项
            for item in restore_list:
                logical_addr = item.get('logical_addr', '')
                slot_symbol = item.get('slot_symbol', '')
                is_dyn_array = item.get('is_dynamic_array', False)
                
                # 【新增】动态数组项
                if is_dyn_array:
                    hashtable_symbol = item.get('hashtable_symbol', '')
                    size_symbol = item.get('size_symbol', '')
                    
                    f.write(f'    .word 0xFFF0  ; 动态数组标记: {logical_addr}\n')
                    f.write(f'    .word {hashtable_symbol}  ; 哈希表地址\n')
                    f.write(f'    .word {size_symbol}  ; 大小变量地址\n')
                    continue  # ← 跳过常规恢复逻辑
                
                # 【原有】标准栈变量
                if '::SP+' in logical_addr:
                    func_name = logical_addr.split('::SP+')[0]
                    offset = int(logical_addr.split('::SP+')[1])
                    sp_adjustment = func_sp_adjustments.get(func_name, 0)
                    
                    f.write(f'    .word {sp_adjustment}  ; SP调整: {logical_addr}\n')
                    f.write(f'    .word {slot_symbol}  ; FRAM地址\n')
                    f.write(f'    .word {offset}  ; 栈偏移\n')
            
            # 返回地址标记
            f.write(f'    .word 0xFFFF  ; 返回地址标记\n')
            
            if wid_function and wid_function not in ['main', 'init']:
                ret_symbol = f'RET_ADDR_{wid_function.upper()}'
                func_info = function_info.get(wid_function, {})
                ret_offset = func_info.get('stack_size', 0) or 20
                
                f.write(f'    .word 0  ; SP调整（返回地址）\n')
                f.write(f'    .word {ret_symbol}  ; 返回地址FRAM\n')
                f.write(f'    .word {ret_offset}  ; 返回地址偏移\n')
            else:
                f.write(f'    .word 0  ; 无返回地址\n')
                f.write(f'    .word 0\n')
                f.write(f'    .word 0\n')
            
            f.write(f'    .word 0  ; PC占位\n')
            f.write(f'    .word 0  ; 结束标记\n\n')
        
        # ======= WID跳转表 =======
        f.write('; WID 跳转表\n')
        f.write('_restore_table:\n')
        
        for wid_data in ranges:
            wid = wid_data['wid']
            list_id = wid_to_list_id[wid]
            pc_value_raw = wid_pc_map.get(wid, '0x0000')
            if isinstance(pc_value_raw, str) and len(pc_value_raw) > 6:
                pc_value = '0x' + pc_value_raw[-4:]
            else:
                pc_value = pc_value_raw
            
            f.write(f'    .word _unique_restore_list_{list_id}  ; {wid}\n')
            f.write(f'    .word {pc_value}\n')
        
        # ======= 恢复逻辑代码 =======
        f.write('\n    .section .text\n')
        f.write('    .align 2\n\n')
        
        f.write('_asap_restore:\n')
        f.write('    MOV.W &ASAP_WID_SAVE, R12\n')
        f.write('    CMP.W #0, R12\n')
        f.write('    JEQ _restore_end\n')
        f.write(f'    CMP.W #{len(ranges)+1}, R12\n')
        f.write('    JGE _restore_end\n\n')
        
        f.write('    ; 查表\n')
        f.write('    DEC.W R12\n')
        f.write('    RLA.W R12\n')
        f.write('    RLA.W R12\n')
        f.write('    ADD.W #_restore_table, R12\n')
        f.write('    MOV.W @R12+, R14  ; R14 = 恢复表指针\n')
        f.write('    MOV.W @R12, R15   ; R15 = PC\n')
        f.write('    MOV.W R15, &ASAP_PC_SAVE\n\n')
        
        f.write('_restore_items:\n')
        f.write('    MOV.W @R14+, R15\n')
        f.write('    CMP.W #0xFFFF, R15\n')
        f.write('    JEQ _restore_return_addr\n')
        f.write('    CMP.W #0xFFFE, R15\n')
        f.write('    JEQ _restore_indirect\n')
        f.write('    CMP.W #0xFFFD, R15\n')
        f.write('    JEQ _restore_redirect_ind\n')
        
        # 【新增】动态数组恢复分支
        f.write('    CMP.W #0xFFF0, R15\n')
        f.write('    JEQ _restore_dynamic_array\n\n')
        
        # 【原有】标准栈变量恢复
        f.write('    ; 标准栈变量恢复\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11\n')
        f.write('    ADD.W R15, R11\n')
        f.write('    MOV.W @R14+, R10\n')
        f.write('    MOV.W @R10, R13\n')
        f.write('    MOV.W @R14+, R9\n')
        f.write('    ADD.W R9, R11\n')
        f.write('    CMP.W #0x2400, R11\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R11\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R13, 0(R11)\n')
        f.write('    JMP _restore_items\n\n')
        
        # 【原有】间接寻址恢复（简化版）
        f.write('_restore_indirect:\n')
        f.write('    MOV.W @R14+, R8\n')
        f.write('    MOV.W @R8, R9\n')
        f.write('    MOV.W @R14+, R8\n')
        f.write('    MOV.W @R8, R8\n')
        f.write('    ADD.W #2, R14\n')
        f.write('    MOV.W R9, 0(R8)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_redirect_ind:\n')
        f.write('    ADD.W #10, R14  ; 跳过6个字\n')
        f.write('    JMP _restore_items\n\n')
        
        # 【新增】动态数组恢复分支
        f.write('; ============================================\n')
        f.write('; 动态数组哈希表恢复\n')
        f.write('; ============================================\n')
        f.write('_restore_dynamic_array:\n')
        f.write('    ; R14指向[hashtable_addr_word, size_addr_word]\n')
        f.write('    MOV.W @R14+, R15  ; R15 = hashtable_symbol地址\n')
        f.write('    MOV.W @R14+, R12  ; R12 = size_symbol地址（暂时不用）\n')
        f.write('    \n')
        f.write('    ; 调用哈希表恢复函数\n')
        f.write('    ; 输入: R15 = hashtable_base\n')
        f.write('    CALL #__asap_hashtable_restore\n')
        f.write('    \n')
        f.write('    ; 继续处理下一个恢复项\n')
        f.write('    JMP _restore_items\n\n')
        
        # 【原有】返回地址恢复
        f.write('_restore_return_addr:\n')
        f.write('    MOV.W @R14+, R15\n')
        f.write('    MOV.W @R14+, R10\n')
        f.write('    CMP.W #0, R10\n')
        f.write('    JEQ _restore_skip_ret_addr\n')
        f.write('    MOV.W @R14+, R9\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11\n')
        f.write('    ADD.W R15, R11\n')
        f.write('    MOV.W @R10, R13\n')
        f.write('    ADD.W R11, R9\n')
        f.write('    MOV.W R13, 0(R9)\n')
        f.write('    JMP _restore_pc\n')
        
        f.write('_restore_skip_ret_addr:\n')
        f.write('    ADD.W #2, R14\n')
        
        f.write('_restore_pc:\n')
        f.write('    MOV.W @R14+, R15  ; PC\n')
        f.write('    ADD.W #2, R14     ; 跳过结束标记\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R1\n')
        f.write('    MOV.W #1, &__asap_restored_flag\n')
        f.write('    BR R15\n\n')
        
        f.write('_restore_end:\n')
        f.write('    RET\n\n')
        
        f.write('    .end\n')


def main():
    parser = argparse.ArgumentParser(description='Stage 11: 生成恢复逻辑 + 动态数组')
    parser.add_argument('--pc-ranges', required=True, help='PC范围JSON')
    parser.add_argument('--wid-pc-map', required=True, help='WID→PC映射JSON')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位JSON')
    parser.add_argument('--function-info', required=True, help='函数信息JSON')
    parser.add_argument('--output', default='build/asap_restore.s', help='输出汇编')
    parser.add_argument('--format', default='asm', choices=['asm', 'c'], help='输出格式')
    
    args = parser.parse_args()
    
    # 加载数据
    pc_ranges_data, fram_slots = load_pc_ranges_with_array_info(args.pc_ranges, args.fram_slots)
    
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    with open(args.function_info, 'r') as f:
        function_info = json.load(f)
    
    wid_backup_regs = {}
    
    # 生成恢复代码
    if args.format == 'asm':
        generate_restore_asm_with_array(
            pc_ranges_data, wid_pc_map, fram_slots, 
            function_info, wid_backup_regs, args.output
        )
    
    print(f"  ✓ 恢复逻辑生成完成（支持动态数组）")
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()


