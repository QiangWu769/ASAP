#!/usr/bin/env python3
"""
Stage 11: 生成恢复逻辑（表驱动 + 去重优化）

优化策略：
1. 识别相同的恢复列表（基于内容哈希）
2. 为每个唯一的恢复列表只生成一次代码
3. 让多个 WID 共享同一个恢复列表
4. 大幅减少代码冗余，节省 Flash 空间

输入: build/pc_ranges.json
输出: build/asap_restore.s
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

def restore_list_to_tuple(restore_list, call_stack=None):
    """将恢复列表转换为可哈希的元组，用于去重
    
    【关键修复】同时考虑调用栈深度，避免不同调用深度的WID被错误合并
    例如：W001（在cf_rand内）和W017（在insert内）虽然恢复的变量相同，
    但需要恢复的返回地址不同，不能共享同一个恢复列表
    """
    items = []
    for item in restore_list:
        # 只比较逻辑地址和槽位地址，这是恢复的核心内容
        logical_addr = item.get('logical_addr', '')
        slot_addr = item.get('slot_addr', '')
        redirect_target = item.get('redirect_target', '')
        items.append((logical_addr, slot_addr, redirect_target))
    
    # 【关键】将调用栈也加入哈希，不同调用深度的WID不能共享恢复列表
    call_stack_tuple = tuple(call_stack) if call_stack else ()
    
    return (tuple(items), call_stack_tuple)

def generate_restore_asm_dedup(pc_ranges_data, wid_pc_map, fram_slots_data, function_info, wid_backup_regs, output_path, loop_arrays_data=None, candidates_data=None):
    """生成汇编格式的恢复逻辑（去重优化版）
    
    标记说明（用于区分字节/字操作）：
    - 0xFFFC: 间接栈写入（字，MOV.W）
    - 0xFFFA: 间接栈写入（字节，MOV.B）
    - 0xFFFE: 间接寻址（字）
    - 0xFFF9: 间接寻址（字节）
    - 普通栈变量：SP调整>=0 为字，<0 为字节（用绝对值）
    """
    
    # 【辅助函数】获取WID的mnemonic
    def get_mnemonic(wid):
        if candidates_data and wid in candidates_data:
            return candidates_data[wid].get('mnemonic', 'MOV.W')
        return 'MOV.W'
    
    def is_byte_op(wid):
        mnemonic = get_mnemonic(wid)
        return '.B' in mnemonic.upper()
    
    # 【新增】建立 logical_addr → mnemonic 的映射
    # 因为同一个 logical_addr 可能对应多个 WID（共享恢复列表）
    # 但它们的 mnemonic 应该相同
    logical_addr_to_mnemonic = {}
    if candidates_data:
        for wid, info in candidates_data.items():
            logical_addr = info.get('logical_addr', '')
            mnemonic = info.get('mnemonic', 'MOV.W')
            if logical_addr and logical_addr not in logical_addr_to_mnemonic:
                logical_addr_to_mnemonic[logical_addr] = mnemonic
    
    def is_byte_op_by_addr(logical_addr):
        """根据 logical_addr 判断是否是字节操作"""
        mnemonic = logical_addr_to_mnemonic.get(logical_addr, 'MOV.W')
        return '.B' in mnemonic.upper()
    
    ranges = pc_ranges_data.get('ranges', [])
    
    # ======= 第一步：识别唯一的恢复列表 =======
    print("  [去重] 分析恢复列表相似性...")
    unique_lists = {}  # {restore_tuple: {'id': int, 'wids': [str], 'restore_list': [...]}}
    wid_to_list_id = {}  # {wid: list_id}
    
    for wid_data in ranges:
        wid = wid_data['wid']
        restore_list = wid_data.get('restore_list', [])
        call_stack = wid_data.get('call_stack', [])
        
        # 【关键修复】将调用栈也传入，确保不同调用深度的WID使用不同的恢复列表
        restore_tuple = restore_list_to_tuple(restore_list, call_stack)
        
        if restore_tuple not in unique_lists:
            list_id = len(unique_lists) + 1
            
            # 【修复】从call_stack获取断电时所在的函数（最后一个元素）
            call_stack = wid_data.get('call_stack', [])
            wid_function = call_stack[-1] if call_stack else None
            
            # 如果call_stack为空，从第一个恢复项推断（作为回退）
            if not wid_function and restore_list:
                first_addr = restore_list[0]['logical_addr']
                if '::SP+' in first_addr:
                    wid_function = first_addr.split('::')[0]
            
            unique_lists[restore_tuple] = {
                'id': list_id,
                'wids': [],
                'restore_list': restore_list,
                'call_stack': call_stack,
                'wid_function': wid_function
            }
        
        unique_lists[restore_tuple]['wids'].append(wid)
        wid_to_list_id[wid] = unique_lists[restore_tuple]['id']
    
    print(f"  [去重] 找到 {len(ranges)} 个 WID, {len(unique_lists)} 个唯一恢复列表")
    print(f"  [去重] 去重率: {(1 - len(unique_lists) / len(ranges)) * 100:.1f}%")
    
    # 打印去重详情
    for restore_tuple, info in sorted(unique_lists.items(), key=lambda x: len(x[1]['wids']), reverse=True):
        wid_count = len(info['wids'])
        item_count = len(info['restore_list'])
        print(f"  [去重] 恢复列表 #{info['id']}: {item_count} 项, 被 {wid_count} 个 WID 共享")
    
    # ======= 第二步：生成汇编代码 =======
    with open(output_path, 'w') as f:
        # 文件头
        f.write('; ================================================\n')
        f.write('; ASAP 恢复逻辑 - 表驱动实现（去重优化版）\n')
        f.write('; 自动生成 - 请勿手动编辑\n')
        f.write(f'; 总 WID: {len(ranges)}, 唯一恢复列表: {len(unique_lists)}\n')
        f.write(f'; 去重率: {(1 - len(unique_lists) / len(ranges)) * 100:.1f}%\n')
        f.write('; ================================================\n\n')
        
        # 声明外部符号
        f.write('    .global _asap_restore\n')
        f.write('    .extern ASAP_WID_SAVE\n')
        f.write('    .extern ASAP_SP_SAVE\n')
        f.write('    .extern ASAP_PC_SAVE\n')
        
        # 声明寄存器备份槽位（如果有）
        if wid_backup_regs:
            regs_used = set(wid_backup_regs.values())
            for reg in sorted(regs_used):
                f.write(f'    .extern __SLOT_REG_{reg}\n')
        f.write('\n')
        
        # 使用.comm定义恢复标志（避免重复定义）
        f.write('    .comm __asap_restored_flag, 2, 2  ; 恢复标志（SRAM BSS，2字节）\n\n')
        
        # 恢复表数据段
        f.write('    .section .rodata\n')
        f.write('    .align 2\n\n')
        
        # 收集所有函数名（用于声明SP外部符号）
        all_functions = set()
        for info in unique_lists.values():
            for var_item in info['restore_list']:
                logical_addr = var_item.get('logical_addr', '')
                if '::SP+' in logical_addr:
                    func_name = logical_addr.split('::SP+')[0]
                    all_functions.add(func_name)
        
        # ======= 生成唯一的恢复列表（去重） =======
        f.write('; 唯一恢复列表（去重后）：每个恢复列表只生成一次\n')
        
        for restore_tuple, info in sorted(unique_lists.items(), key=lambda x: x[1]['id']):
            list_id = info['id']
            restore_list = info['restore_list']
            wid_function = info['wid_function']
            call_stack = info['call_stack']
            
            f.write(f'; 恢复列表 #{list_id}: {len(restore_list)} 项, 被 {len(info["wids"])} 个 WID 共享\n')
            f.write(f'; 共享 WID: {", ".join(info["wids"])}\n')
            f.write(f'_unique_restore_list_{list_id}:\n')
            
            # 确定调用栈
            if not call_stack and wid_function:
                call_stack = [wid_function]
            
            # 预计算每个函数的SP调整量
            func_sp_adjustments = {}
            current_adjustment = 0
            
            for i in range(len(call_stack) - 1, -1, -1):
                func_name = call_stack[i]
                func_sp_adjustments[func_name] = current_adjustment
                
                if i > 0:
                    frame_size = function_info.get(func_name, {}).get('stack_size', 0)
                    current_adjustment += frame_size + 2
            
            # 收集重定向信息
            redirected_targets = set()
            for item in restore_list:
                redirect_target = item.get('redirect_target', '')
                if redirect_target:
                    redirected_targets.add(redirect_target)
            
            # 记录最大栈偏移（用于返回地址）
            max_offset_per_func = {}
            
            # 生成恢复项
            for item in restore_list:
                logical_addr = item.get('logical_addr', '')
                slot_symbol = item.get('slot_symbol', '')
                redirect_target = item.get('redirect_target', '')
                
                # 跳过被重定向的项
                if logical_addr in redirected_targets:
                    continue
                
                # 判断是否为重定向的间接寻址
                is_redirect_indirect = bool(redirect_target and '::SP+' in redirect_target)
                
                # 判断是否为标准间接寻址
                is_indirect = logical_addr.startswith('*') and not is_redirect_indirect
                
                if is_redirect_indirect:
                    # 重定向间接寻址：[0xFFFD, value_slot, target_sp_adj, target_offset, indirect_offset, reg]
                    target_func = redirect_target.split('::SP+')[0]
                    target_offset_str = redirect_target.split('::SP+')[1]
                    
                    try:
                        if '+' in target_offset_str:
                            parts = target_offset_str.split('+')
                            target_offset = int(parts[0])
                            indirect_offset = int(parts[1])
                        else:
                            target_offset = int(target_offset_str)
                            indirect_offset = 0
                    except ValueError:
                        target_offset = 0
                        indirect_offset = 0
                    
                    target_sp_adj = func_sp_adjustments.get(target_func, 0)
                    
                    f.write(f'    .word 0xFFFD  ; 重定向间接寻址: {logical_addr} → {redirect_target}\n')
                    f.write(f'    .word {slot_symbol}  ; 值的FRAM地址\n')
                    f.write(f'    .word {target_sp_adj}  ; 目标函数SP调整\n')
                    f.write(f'    .word {target_offset}  ; 目标栈偏移\n')
                    f.write(f'    .word {indirect_offset}  ; 间接偏移\n')
                    f.write(f'    .word 0  ; 寄存器编号（保留）\n')
                
                elif is_indirect:
                    # 标准间接寻址：[0xFFFE, value_slot, addr_slot, reg]
                    # 【修复】字节操作使用 0xFFF9
                    clean_addr = logical_addr[1:]
                    if '::SP+' in clean_addr:
                        func_name, offset_str = clean_addr.split('::SP+')
                        offset = int(offset_str)
                    else:
                        func_name = None
                        offset = 0
                    
                    addr_symbol = f'__SLOT_ADDR_{slot_symbol[7:]}'
                    
                    # 检查是否是字节操作
                    is_byte = is_byte_op_by_addr(logical_addr.lstrip('*'))
                    marker = '0xFFF9' if is_byte else '0xFFFE'
                    op_type = 'MOV.B' if is_byte else 'MOV.W'
                    
                    f.write(f'    .word {marker}  ; 间接寻址({op_type}): {logical_addr}\n')
                    f.write(f'    .word {slot_symbol}  ; 值的FRAM地址\n')
                    f.write(f'    .word {addr_symbol}  ; 目标地址的FRAM地址\n')
                    f.write(f'    .word 0  ; 寄存器编号（保留）\n')
                
                elif item.get('addr_mode') == 'INDIRECT_STACK':
                    # 【新增】间接栈写入（动态索引）：[0xFFFC, value_slot, addr_slot]
                    # 恢复时：从addr_slot读取实际地址，然后把value写入该地址
                    # 【修复】字节操作使用 0xFFFA
                    addr_slot_symbol = item.get('addr_slot_symbol', '')
                    if addr_slot_symbol:
                        # 检查是否是字节操作
                        is_byte = is_byte_op_by_addr(logical_addr)
                        marker = '0xFFFA' if is_byte else '0xFFFC'
                        op_type = 'MOV.B' if is_byte else 'MOV.W'
                        
                        f.write(f'    .word {marker}  ; 间接栈写入({op_type}): {logical_addr}\n')
                        f.write(f'    .word {slot_symbol}  ; 值的FRAM地址\n')
                        f.write(f'    .word {addr_slot_symbol}  ; 写入地址的FRAM地址\n')
                    else:
                        # 如果没有地址槽位，回退到标准恢复（可能有问题但至少不会崩溃）
                        f.write(f'    ; ⚠ 警告: {logical_addr} 是INDIRECT_STACK但缺少addr_slot_symbol\n')
                        # 尝试作为标准栈变量恢复
                        if '::SP+' in logical_addr:
                            func_name, offset_str = logical_addr.split('::SP+')
                            try:
                                offset = int(offset_str)
                            except ValueError:
                                offset = eval(offset_str)
                            sp_adjustment = func_sp_adjustments.get(func_name, 0)
                            f.write(f'    .word {sp_adjustment}  ; SP调整量（回退）: {logical_addr}\n')
                            f.write(f'    .word {slot_symbol}  ; FRAM地址\n')
                            f.write(f'    .word {offset}  ; 栈偏移\n')
                
                elif item.get('addr_mode') == 'SRAM_GLOBAL':
                    # 【新增】SRAM全局变量：[0xFFFB, FRAM槽位, SRAM地址]
                    # 恢复时：从FRAM槽位读取值，写入SRAM地址
                    sram_addr = item.get('sram_addr', '0x1C00')
                    # 如果是符号名，需要添加&前缀
                    if not (sram_addr.startswith('0x') or sram_addr.startswith('0X')):
                        sram_addr_ref = f'{sram_addr}'  # 符号名直接使用
                    else:
                        sram_addr_ref = sram_addr
                    f.write(f'    .word 0xFFFB  ; SRAM全局变量: {logical_addr}\n')
                    f.write(f'    .word {slot_symbol}  ; 值的FRAM地址\n')
                    f.write(f'    .word {sram_addr_ref}  ; SRAM目标地址\n')
                
                else:
                    # 标准栈变量：[SP调整, FRAM地址, 偏移]
                    # 【修复】字节操作使用 [0xFFF8, SP调整, FRAM地址, 偏移]
                    if '::SP+' in logical_addr:
                        func_name, offset_str = logical_addr.split('::SP+')
                        # 处理可能的表达式如 '7+2'
                        try:
                            offset = int(offset_str)
                        except ValueError:
                            offset = eval(offset_str)  # 安全处理简单的算术表达式
                        
                        sp_adjustment = func_sp_adjustments.get(func_name, 0)
                        
                        max_offset_per_func[func_name] = max(max_offset_per_func.get(func_name, 0), offset)
                        
                        # 检查是否是字节操作
                        is_byte = is_byte_op_by_addr(logical_addr)
                        if is_byte:
                            # 字节操作：使用特殊标记
                            f.write(f'    .word 0xFFF8  ; 栈变量(MOV.B): {logical_addr}\n')
                            f.write(f'    .word {sp_adjustment}  ; SP调整量\n')
                            f.write(f'    .word {slot_symbol}  ; FRAM地址\n')
                            f.write(f'    .word {offset}  ; 栈偏移\n')
                        else:
                            # 字操作：保持原格式
                            f.write(f'    .word {sp_adjustment}  ; SP调整量: {logical_addr}\n')
                            f.write(f'    .word {slot_symbol}  ; FRAM地址\n')
                            f.write(f'    .word {offset}  ; 栈偏移\n')
                    elif '::R' in logical_addr:
                        # 【修复】检查是否是全局数组写入
                        # 如果是全局数组写入，跳过（由镜像恢复）
                        # 如果不是，使用 __ADDR_ 恢复
                        import re
                        match = re.match(r'(\w+)::R(\d+)\+(\d+)', logical_addr)
                        if match:
                            func_name = match.group(1)
                            reg_num = match.group(2)
                            offset = int(match.group(3))
                            
                            # 检查是否是全局数组写入
                            is_global_array_write = False
                            if loop_arrays_data:
                                writes = loop_arrays_data.get('writes', {})
                                for wid_key, write_info in writes.items():
                                    if write_info.get('logical_addr') == logical_addr:
                                        array_name = write_info.get('array_name', '')
                                        arrays = loop_arrays_data.get('arrays', {})
                                        if array_name in arrays and arrays[array_name].get('is_global', False):
                                            is_global_array_write = True
                                            f.write(f'    ; 【跳过】{logical_addr}: 全局数组 {array_name} 写入，由镜像恢复\n')
                                            break
                            
                            if is_global_array_write:
                                continue  # 跳过全局数组写入，由镜像机制恢复
                            
                            # 非全局数组写入：使用地址备份恢复间接寻址
                            # 格式: func::R12+2 → 从 __ADDR_func_R12_0 读基地址，加 offset
                            # 基地址槽位: __ADDR_func_R12_0
                            base_addr_slot = f'__ADDR_{func_name}_R{reg_num}_0'
                            # 值槽位: 使用实际的 slot_symbol
                            value_slot = slot_symbol
                            
                            # 【修复】检查是否是字节操作
                            is_byte = is_byte_op_by_addr(logical_addr)
                            marker = '0xFFF9' if is_byte else '0xFFFE'
                            op_type = 'MOV.B' if is_byte else 'MOV.W'
                            
                            # 生成间接寻址恢复: [0xFFFE/0xFFF9, value_slot, base_addr_slot, offset]
                            f.write(f'    .word {marker}  ; 间接寻址恢复({op_type}): {logical_addr}\n')
                            f.write(f'    .word {value_slot}  ; 值的FRAM地址\n')
                            f.write(f'    .word {base_addr_slot}  ; 基地址的FRAM地址\n')
                            f.write(f'    .word {offset}  ; 偏移量\n')
                        else:
                            f.write(f'    ; 【跳过】{logical_addr}: 无法解析的间接寻址格式\n')
                            continue
                    else:
                        # 全局变量（不常见）
                        f.write(f'    .word 0  ; 全局变量: {logical_addr}\n')
                        f.write(f'    .word {slot_symbol}  ; FRAM地址\n')
                        f.write(f'    .word 0  ; 无偏移\n')
            
            # 【关键修复】恢复调用栈上所有函数的返回地址
            # 调用栈从根到叶：main → caller → ... → wid_function
            # 需要恢复除了main以外所有函数的返回地址
            f.write(f'    .word 0xFFFF  ; 返回地址标记\n')
            
            # 从叶到根遍历调用栈，恢复每个函数的返回地址（main除外）
            ret_addr_count = 0
            for i in range(len(call_stack) - 1, -1, -1):
                func_name = call_stack[i]
                if func_name in ['main', 'init']:
                    continue  # main和init没有返回地址需要恢复
                
                ret_symbol = f'RET_ADDR_{func_name.upper()}'
                func_info_item = function_info.get(func_name, {})
                ret_offset = func_info_item.get('stack_size', 0)
                
                if ret_offset == 0:
                    max_offset = max_offset_per_func.get(func_name, 0)
                    ret_offset = max_offset + 4
                
                # SP调整量：从断电函数SP到该函数SP的偏移
                sp_adj = func_sp_adjustments.get(func_name, 0)
                
                f.write(f'    .word {sp_adj}  ; SP调整量（{func_name}返回地址）\n')
                f.write(f'    .word {ret_symbol}  ; 返回地址FRAM地址\n')
                f.write(f'    .word {ret_offset}  ; 返回地址栈偏移\n')
                ret_addr_count += 1
            
            # 返回地址结束标记：SP调整=0, FRAM地址=0表示结束
            f.write(f'    .word 0  ; 返回地址结束标记\n')
            f.write(f'    .word 0  ; FRAM地址=0表示没有更多返回地址\n')
            f.write(f'    .word 0  ; 占位符\n')
            
            # 不在这里写 PC，而是在跳转表中为每个 WID 单独指定
            f.write(f'    .word 0  ; PC 占位符（在跳转表中指定）\n')
            f.write(f'    .word 0  ; 结束标记\n\n')
        
        # ======= WID → 恢复表指针 + PC 的跳转表 =======
        f.write('; WID 跳转表：每个 WID 包含 [恢复列表指针, PC]\n')
        f.write('_restore_table:\n')
        
        for wid_data in ranges:
            wid = wid_data['wid']
            list_id = wid_to_list_id[wid]
            
            # 获取这个 WID 的 PC
            pc_value_raw = wid_pc_map.get(wid, '0x0000')
            if isinstance(pc_value_raw, str) and len(pc_value_raw) > 6:
                pc_value = '0x' + pc_value_raw[-4:]
            else:
                pc_value = pc_value_raw
            
            f.write(f'    .word _unique_restore_list_{list_id}  ; {wid} → 列表 #{list_id}\n')
            f.write(f'    .word {pc_value}  ; {wid} 的恢复 PC\n')
        
        # ======= 恢复逻辑代码 =======
        f.write('\n    .section .text\n')
        f.write('    .align 2\n\n')
        
        f.write('_asap_restore:\n')
        f.write('    ; 从FRAM读取WID\n')
        f.write('    MOV.W &ASAP_WID_SAVE, R12\n')
        f.write('    ; 检查WID有效性\n')
        f.write('    CMP.W #0, R12\n')
        f.write('    JEQ _restore_end           ; WID=0 → 放弃\n')
        f.write(f'    CMP.W #{len(ranges)+1}, R12\n')
        f.write('    JGE _restore_end           ; WID超范围 → 放弃\n\n')
        
        f.write('    ; 查表：R14 = 恢复列表指针, R15 = PC\n')
        f.write('    DEC.W R12                  ; R12 = WID-1\n')
        f.write('    RLA.W R12                  ; R12 = (WID-1)*2\n')
        f.write('    RLA.W R12                  ; R12 = (WID-1)*4 (每项4字节)\n')
        f.write('    ADD.W #_restore_table, R12 ; R12 = table地址\n')
        f.write('    MOV.W @R12+, R14           ; R14 = 恢复表指针\n')
        f.write('    MOV.W @R12, R15            ; R15 = 恢复PC\n')
        f.write('    MOV.W R15, &ASAP_PC_SAVE   ; 保存PC到FRAM\n\n')
        
        f.write('_restore_items:\n')
        f.write('    ; 恢复循环：支持 MOV.B/MOV.W 区分\n')
        f.write('    ; 标记: 0xFFFF=结束, 0xFFFE=间接(W), 0xFFF9=间接(B), 0xFFFD=重定向,\n')
        f.write('    ;       0xFFFC=间接栈(W), 0xFFFA=间接栈(B), 0xFFFB=SRAM全局, 0xFFF8=栈变量(B)\n')
        f.write('    MOV.W @R14+, R15           ; R15 = 标记/SP调整量\n')
        f.write('    CMP.W #0xFFFF, R15         ; 结束标记？\n')
        f.write('    JEQ _restore_return_addr   ; 是→处理返回地址\n')
        f.write('    CMP.W #0xFFFE, R15         ; 间接寻址标记(MOV.W)？\n')
        f.write('    JEQ _restore_indirect      ; 是→处理间接寻址(字)\n')
        f.write('    CMP.W #0xFFF9, R15         ; 间接寻址标记(MOV.B)？\n')
        f.write('    JEQ _restore_indirect_byte ; 是→处理间接寻址(字节)\n')
        f.write('    CMP.W #0xFFFD, R15         ; 重定向间接寻址标记？\n')
        f.write('    JEQ _restore_redirect_ind  ; 是→处理重定向间接寻址\n')
        f.write('    CMP.W #0xFFFC, R15         ; 间接栈写入标记(MOV.W)？\n')
        f.write('    JEQ _restore_indirect_stack ; 是→处理间接栈写入(字)\n')
        f.write('    CMP.W #0xFFFA, R15         ; 间接栈写入标记(MOV.B)？\n')
        f.write('    JEQ _restore_indirect_stack_byte ; 是→处理间接栈写入(字节)\n')
        f.write('    CMP.W #0xFFFB, R15         ; SRAM全局变量标记？\n')
        f.write('    JEQ _restore_sram_global   ; 是→处理SRAM全局变量\n')
        f.write('    CMP.W #0xFFF8, R15         ; 栈变量(MOV.B)标记？\n')
        f.write('    JEQ _restore_stack_byte    ; 是→处理栈变量(字节)\n')
        
        f.write('    ; 【标准栈变量恢复】\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电SP\n')
        f.write('    ADD.W R15, R11             ; R11 = 目标函数SP\n')
        f.write('    MOV.W @R14+, R10           ; R10 = FRAM槽位地址\n')
        f.write('    MOV.W @R10, R13            ; R13 = FRAM中的值\n')
        f.write('    MOV.W @R14+, R9            ; R9 = 栈偏移量\n')
        f.write('    MOV.W R11, R15             ; R15 = 目标函数SP\n')
        f.write('    ADD.W R9, R15              ; R15 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R15\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R15\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R13, 0(R15)          ; 写入\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_indirect:\n')
        f.write('    ; 【间接寻址恢复(字) - 支持偏移】\n')
        f.write('    ; 格式: [0xFFFE, value_slot, base_addr_slot, offset]\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 基地址的FRAM地址\n')
        f.write('    MOV.W @R8, R8              ; R8 = 基地址\n')
        f.write('    MOV.W @R14+, R10           ; R10 = 偏移量\n')
        f.write('    ADD.W R10, R8              ; R8 = 基地址 + 偏移 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R8\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R8\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R9, 0(R8)            ; 写入(字)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_indirect_byte:\n')
        f.write('    ; 【间接寻址恢复(字节)】\n')
        f.write('    ; 格式: [0xFFF9, value_slot, base_addr_slot, offset]\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.B @R8, R9              ; R9 = 值(字节)\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 基地址的FRAM地址\n')
        f.write('    MOV.W @R8, R8              ; R8 = 基地址\n')
        f.write('    MOV.W @R14+, R10           ; R10 = 偏移量\n')
        f.write('    ADD.W R10, R8              ; R8 = 基地址 + 偏移 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R8\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R8\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.B R9, 0(R8)            ; 写入(字节)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_redirect_ind:\n')
        f.write('    ; 【重定向间接寻址】\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 目标SP调整\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R10   ; R10 = 断电SP\n')
        f.write('    ADD.W R8, R10              ; R10 += SP调整\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 目标栈偏移\n')
        f.write('    ADD.W R8, R10              ; R10 += 栈偏移\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 间接偏移\n')
        f.write('    ADD.W R8, R10              ; R10 = 最终目标地址\n')
        f.write('    ADD.W #2, R14              ; 跳过寄存器编号\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R10\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R10\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.W R9, 0(R10)           ; 写入\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_indirect_stack:\n')
        f.write('    ; 【间接栈写入(字)】\n')
        f.write('    ; 格式：[0xFFFC, value_slot, addr_slot]\n')
        f.write('    ; 恢复：从addr_slot读取实际地址，把value写入该地址\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 地址的FRAM地址\n')
        f.write('    MOV.W @R8, R10             ; R10 = 实际写入地址\n')
        f.write('    ; 安全检查：确保地址在SRAM范围内（0x1C00-0x2400）\n')
        f.write('    CMP.W #0x2400, R10\n')
        f.write('    JHS _restore_items         ; 地址超出范围，跳过\n')
        f.write('    CMP.W #0x1C00, R10\n')
        f.write('    JLO _restore_items         ; 地址超出范围，跳过\n')
        f.write('    MOV.W R9, 0(R10)           ; 写入(字)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_indirect_stack_byte:\n')
        f.write('    ; 【间接栈写入(字节)】\n')
        f.write('    ; 格式：[0xFFFA, value_slot, addr_slot]\n')
        f.write('    ; 恢复：从addr_slot读取实际地址，把value(字节)写入该地址\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 值的FRAM地址\n')
        f.write('    MOV.B @R8, R9              ; R9 = 值(字节)\n')
        f.write('    MOV.W @R14+, R8            ; R8 = 地址的FRAM地址\n')
        f.write('    MOV.W @R8, R10             ; R10 = 实际写入地址\n')
        f.write('    ; 安全检查：确保地址在SRAM范围内（0x1C00-0x2400）\n')
        f.write('    CMP.W #0x2400, R10\n')
        f.write('    JHS _restore_items         ; 地址超出范围，跳过\n')
        f.write('    CMP.W #0x1C00, R10\n')
        f.write('    JLO _restore_items         ; 地址超出范围，跳过\n')
        f.write('    MOV.B R9, 0(R10)           ; 写入(字节)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_sram_global:\n')
        f.write('    ; 【全局变量恢复】\n')
        f.write('    ; 格式：[0xFFFB, FRAM槽位, 目标地址]\n')
        f.write('    ; 恢复：从FRAM槽位读取值，写入目标地址\n')
        f.write('    ; 注意：目标可能是SRAM(0x1C00-0x2400)或FRAM(.data段)变量\n')
        f.write('    MOV.W @R14+, R8            ; R8 = FRAM槽位地址\n')
        f.write('    MOV.W @R8, R9              ; R9 = 值\n')
        f.write('    MOV.W @R14+, R10           ; R10 = 目标地址\n')
        f.write('    ; 安全检查：确保地址有效（非0，非外设区域）\n')
        f.write('    CMP.W #0, R10\n')
        f.write('    JEQ _restore_items         ; 地址无效，跳过\n')
        f.write('    CMP.W #0x200, R10\n')
        f.write('    JLO _restore_items         ; 外设区域，跳过\n')
        f.write('    MOV.W R9, 0(R10)           ; 写入目标地址\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_stack_byte:\n')
        f.write('    ; 【栈变量恢复(字节)】\n')
        f.write('    ; 格式：[0xFFF8, SP调整, FRAM地址, 偏移]\n')
        f.write('    MOV.W @R14+, R15           ; R15 = SP调整量\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电SP\n')
        f.write('    ADD.W R15, R11             ; R11 = 目标函数SP\n')
        f.write('    MOV.W @R14+, R10           ; R10 = FRAM槽位地址\n')
        f.write('    MOV.B @R10, R13            ; R13 = FRAM中的值(字节)\n')
        f.write('    MOV.W @R14+, R9            ; R9 = 栈偏移量\n')
        f.write('    MOV.W R11, R15             ; R15 = 目标函数SP\n')
        f.write('    ADD.W R9, R15              ; R15 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R15\n')
        f.write('    JHS _restore_items\n')
        f.write('    CMP.W #0x1C00, R15\n')
        f.write('    JLO _restore_items\n')
        f.write('    MOV.B R13, 0(R15)          ; 写入(字节)\n')
        f.write('    JMP _restore_items\n\n')
        
        f.write('_restore_return_addr:\n')
        f.write('    ; 【关键修复】循环处理调用栈上所有函数的返回地址\n')
        f.write('    ; 格式：[SP调整, FRAM地址, 偏移], ..., [0, 0, 0]表示结束\n')
        f.write('_restore_ret_loop:\n')
        f.write('    MOV.W @R14+, R15       ; R15 = SP调整\n')
        f.write('    MOV.W @R14+, R10       ; R10 = RET_ADDR地址\n')
        f.write('    CMP.W #0, R10          ; FRAM地址=0表示结束\n')
        f.write('    JEQ _restore_skip_ret_addr\n')
        
        f.write('    ; 恢复返回地址\n')
        f.write('    MOV.W @R14+, R9        ; R9 = 偏移\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R11\n')
        f.write('    ADD.W R15, R11         ; R11 = 该函数SP\n')
        f.write('    MOV.W @R10, R13        ; R13 = 返回地址\n')
        f.write('    ADD.W R11, R9          ; R9 = 目标地址\n')
        f.write('    ; 安全检查\n')
        f.write('    CMP.W #0x2400, R9\n')
        f.write('    JHS _restore_ret_loop  ; 地址超出范围，跳过此返回地址，继续下一个\n')
        f.write('    CMP.W #0x1C00, R9\n')
        f.write('    JLO _restore_ret_loop  ; 地址超出范围，跳过此返回地址，继续下一个\n')
        f.write('    MOV.W R13, 0(R9)       ; 写入返回地址\n')
        f.write('    JMP _restore_ret_loop  ; 继续处理下一个返回地址\n\n')
        
        f.write('_restore_skip_ret_addr:\n')
        f.write('    ADD.W #2, R14          ; 跳过偏移字段（结束标记的占位符）\n\n')
        
        f.write('_restore_get_pc:\n')
        f.write('    ; 跳过 PC 占位符（已在查表时读取）\n')
        f.write('    ADD.W #2, R14          ; 跳过 PC 字段\n\n')
        
        f.write('_restore_sp:\n')
        f.write('    ; 恢复栈指针\n')
        f.write('    MOV.W &ASAP_SP_SAVE, SP\n\n')
        
        f.write('_restore_jump:\n')
        f.write('    ; ===== P1.3 置低（标记恢复完成） =====\n')
        f.write('    BIC.B #0x08, &0x0202          ; P1OUT &= ~BIT3 (P1.3置低)\n')
        f.write('    ; 注意：不修改P1.2状态，让应用程序自己管理\n')
        f.write('    ; 【关键修复】清除已恢复标志（而非设置为0x1234）\n')
        f.write('    ; 原因：恢复跳转后会跳过__main_continue处的flag清除代码\n')
        f.write('    ;       如果flag残留为0x1234，下次断电后SRAM可能保留此值\n')
        f.write('    ;       导致误判为"已恢复"而跳过必要的恢复\n')
        f.write('    MOV.W #0, &__asap_restored_flag  ; 清除flag\n')
        
        # 生成寄存器恢复代码（如果有wid_backup_regs映射）
        if wid_backup_regs:
            f.write('\n    ; ===== 恢复寄存器（防止垃圾值覆盖栈） =====\n')
            f.write('    ; WID设置后紧跟的写入可能使用寄存器，需要先恢复\n')
            for wid_num, reg in sorted(wid_backup_regs.items(), key=lambda x: int(x[0])):
                wid_num_int = int(wid_num)
                slot = f'__SLOT_REG_{reg}'
                f.write(f'    CMP.W #{wid_num_int}, &ASAP_WID_SAVE\n')
                f.write(f'    JNE _skip_restore_{reg}_{wid_num_int}\n')
                f.write(f'    MOV.W &{slot}, {reg}    ; 恢复{reg} (WID {wid_num_int}后使用)\n')
                f.write(f'_skip_restore_{reg}_{wid_num_int}:\n')
        
        f.write('    ; 【关键】恢复SP到断电时的值\n')
        f.write('    MOV.W &ASAP_SP_SAVE, R1\n')
        f.write('    ; 清除WID（防止重复恢复）\n')
        f.write('    MOV.W #0, &ASAP_WID_SAVE\n')
        f.write('    ; 跳转到恢复PC\n')
        f.write('    MOV.W &ASAP_PC_SAVE, PC\n\n')
        
        f.write('_restore_end:\n')
        f.write('    ; 冷启动或恢复失败\n')
        f.write('    ; ===== P1.3 保持高（标记恢复失败/异常） =====\n')
        f.write('    ; BIC.B #0x08, &0x0202          ; P1OUT &= ~BIT3 (注释：不置低，保持高作为错误指示)\n')
        f.write('    RET\n\n')

def main():
    parser = argparse.ArgumentParser(description='生成ASAP恢复逻辑（去重优化版）')
    parser.add_argument('--pc-ranges', required=True, help='PC范围数据文件')
    parser.add_argument('--wid-pc-map', required=True, help='WID→PC映射文件')
    parser.add_argument('--fram-slots', required=True, help='FRAM槽位分配文件')
    parser.add_argument('--function-info', required=True, help='函数信息文件')
    parser.add_argument('--wid-backup-regs', default='build/wid_backup_regs.json', help='WID备份寄存器元数据')
    parser.add_argument('--loop-arrays', default='build/loop_arrays.json', help='全局数组信息文件')
    parser.add_argument('--candidates', default='build/candidates.json', help='候选写入信息文件（含mnemonic）')
    parser.add_argument('--output', required=True, help='输出汇编文件')
    parser.add_argument('--format', default='asm', choices=['asm', 'json'], help='输出格式')
    
    args = parser.parse_args()
    
    # 读取输入文件
    with open(args.pc_ranges, 'r') as f:
        pc_ranges_data = json.load(f)
    
    with open(args.wid_pc_map, 'r') as f:
        wid_pc_map = json.load(f)
    
    with open(args.fram_slots, 'r') as f:
        fram_slots_data = json.load(f)
    
    with open(args.function_info, 'r') as f:
        function_info = json.load(f)
    
    # 读取WID备份寄存器元数据（可选）
    wid_backup_regs = {}
    if Path(args.wid_backup_regs).exists():
        with open(args.wid_backup_regs, 'r') as f:
            wid_backup_regs = json.load(f)
    
    # 读取全局数组信息（可选）
    loop_arrays_data = None
    if Path(args.loop_arrays).exists():
        with open(args.loop_arrays, 'r') as f:
            loop_arrays_data = json.load(f)
        print(f'  [加载] 全局数组信息: {args.loop_arrays}')
    
    # 【新增】读取候选写入信息（含mnemonic）
    candidates_data = {}
    if Path(args.candidates).exists():
        with open(args.candidates, 'r') as f:
            candidates_data = json.load(f)
        print(f'  [加载] 候选写入信息: {args.candidates}')
    
    if args.format == 'asm':
        generate_restore_asm_dedup(pc_ranges_data, wid_pc_map, fram_slots_data, 
                                    function_info, wid_backup_regs, args.output, loop_arrays_data, candidates_data)
        print(f'  ✓ 恢复逻辑生成完成（去重优化）: {args.output}')
    else:
        print(f'  ✗ 不支持的输出格式: {args.format}')
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())

