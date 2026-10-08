#!/usr/bin/env python3
"""
Stage 11b: 生成循环数组恢复代码

在_asap_restore中添加：
1. 从FRAM镜像恢复整个数组到栈

输入: build/asap_restore.s, build/loop_arrays.json, build/fram_slots.json
输出: 更新后的 build/asap_restore.s
"""

import argparse
import json
import re
from pathlib import Path

def inject_array_restore(restore_file, loop_arrays_file, fram_slots_file, candidates_file=None):
    """在恢复代码中注入数组恢复逻辑"""
    
    with open(restore_file, 'r') as f:
        content = f.read()
    
    with open(loop_arrays_file, 'r') as f:
        loop_arrays = json.load(f)
    
    with open(fram_slots_file, 'r') as f:
        fram_slots = json.load(f)
    
    # 尝试加载candidates（用于直接栈访问数组）
    candidates = None
    if candidates_file:
        try:
            with open(candidates_file, 'r') as f:
                candidates = json.load(f)
        except:
            pass
    else:
        # 尝试默认路径
        try:
            candidates_path = Path(restore_file).parent / 'candidates.json'
            with open(candidates_path, 'r') as f:
                candidates = json.load(f)
        except:
            pass
    
    array_mirrors = fram_slots.get('array_mirrors', {})
    base_slots = fram_slots.get('array_base_slots', {})
    
    if not array_mirrors:
        print("  没有循环数组需要恢复")
        return
    
    # 生成数组恢复代码
    restore_code = generate_array_restore_code(array_mirrors, base_slots, loop_arrays, fram_slots, candidates)
    
    # 在_restore_sp之前插入数组恢复代码
    # 找到 "_restore_sp:" 标签
    if '_restore_sp:' in content:
        # 在_restore_sp之前插入
        content = content.replace(
            '_restore_sp:',
            restore_code + '\n_restore_sp:'
        )
        print("  ✓ 在_restore_sp前注入数组恢复代码")
    else:
        print("  ⚠ 未找到_restore_sp标签")
    
    # 在文件开头添加外部符号声明
    extern_decls = generate_extern_declarations(array_mirrors, base_slots, loop_arrays)
    
    # 找到第一个 .extern 声明的位置
    extern_match = re.search(r'(\.extern\s+\w+)', content)
    if extern_match:
        insert_pos = extern_match.start()
        content = content[:insert_pos] + extern_decls + '\n' + content[insert_pos:]
    
    with open(restore_file, 'w') as f:
        f.write(content)
    
    print(f"  ✓ 更新: {restore_file}")


def generate_extern_declarations(array_mirrors, base_slots, loop_arrays=None):
    """生成外部符号声明"""
    decls = ["; ===== 循环数组镜像符号 ====="]
    
    for array_name, config in array_mirrors.items():
        decls.append(f"    .extern {config['mirror_symbol']}")
        
        # 对于is_stack_direct数组，还需要声明__backup_xxx_start符号
        if loop_arrays:
            array_info = loop_arrays.get('arrays', {}).get(array_name, {})
            if array_info.get('is_stack_direct'):
                backup_symbol = f"__backup_{array_name}_start"
                decls.append(f"    .extern {backup_symbol}")
    
    for array_name, config in base_slots.items():
        decls.append(f"    .extern {config['symbol']}")
    
    return '\n'.join(decls) + '\n'


def generate_array_restore_code(array_mirrors, base_slots, loop_arrays, fram_slots=None, candidates=None):
    """生成数组恢复的汇编代码
    
    支持两种类型的数组：
    1. INDIRECT_STACK - 通过参数传递的数组（如cf的filter, ar的classModel）
       - 使用__BASE_xxx保存的基地址
       - 完整复制镜像到数组
    
    2. 直接栈访问数组 - 在main中直接访问的数组（如conv的out[], vec[]）
       - 使用stack_offset计算栈地址
       - 增量恢复（只恢复已写入部分）
    """
    
    # 获取每个数组对应的WID范围和第一个WID
    array_wid_ranges = {}
    array_first_wid = {}
    writes = loop_arrays.get('writes', {})
    for wid, info in writes.items():
        array_name = info.get('array_name')
        if array_name:
            if array_name not in array_wid_ranges:
                array_wid_ranges[array_name] = []
            # 提取WID数字
            wid_num = int(wid[1:])  # "W024" -> 24
            array_wid_ranges[array_name].append(wid_num)
            # 记录第一个WID（用于获取addr_slot）
            if array_name not in array_first_wid or wid_num < array_first_wid[array_name][0]:
                array_first_wid[array_name] = (wid_num, wid)
    
    # 【新增】获取每个函数的第一个WID（用于全局数组恢复条件）
    func_first_wid = {}
    if candidates:
        for wid, info in candidates.items():
            func = info.get('function')
            if func:
                wid_num = int(wid[1:])
                if func not in func_first_wid or wid_num < func_first_wid[func]:
                    func_first_wid[func] = wid_num
    
    # 获取每个数组的param_reg和其他信息
    arrays_info = loop_arrays.get('arrays', {})
    
    # 获取addr_slot信息
    wid_to_slot = fram_slots.get('wid_to_slot', {}) if fram_slots else {}
    
    # 从candidates获取数组信息（用于直接栈访问类型）
    # 收集每个数组的所有写入点（支持同一数组多个循环使用不同index_location）
    # 【修复】只收集真正的直接栈访问数组（stack_offset不为None），跳过全局数组
    array_stack_info = {}
    array_wid_index_map = {}  # {array_name: [(wid_num, index_location), ...]}
    if candidates:
        for wid, info in candidates.items():
            if info.get('type') == 'array':
                array_info = info.get('array_info', {})
                array_base = array_info.get('array_base')
                stack_offset = array_info.get('stack_offset')
                
                # 只处理有stack_offset的（直接栈访问），跳过全局数组（stack_offset为None）
                if array_base and stack_offset is not None:
                    wid_num = int(wid[1:])
                    index_loc = array_info.get('index_location', '0(R1)')
                    
                    if array_base not in array_stack_info:
                        array_stack_info[array_base] = {
                            'stack_offset': stack_offset,
                            'index_location': index_loc,
                            'wid': wid
                        }
                        array_wid_index_map[array_base] = []
                    
                    # 记录每个WID对应的index_location
                    array_wid_index_map[array_base].append((wid_num, index_loc))
    
    # 收集所有INDIRECT_STACK WID及其addr_slot（用于R12恢复）
    indirect_stack_wids = []
    array_write_wids = set(writes.keys())  # 数组写入的WID集合
    
    # 【修复】收集全局数组写入的WID，需要从栈重新计算R12
    global_array_write_wids = []
    for wid in array_write_wids:
        write_info = writes.get(wid, {})
        array_name = write_info.get('array_name')
        if array_name:
            array_info = arrays_info.get(array_name, {})
            if array_info.get('is_global', False):
                wid_num = int(wid[1:])
                logical_addr = write_info.get('logical_addr', '')
                global_array_write_wids.append((wid_num, wid, array_name, logical_addr))
    global_array_write_wids.sort(key=lambda x: x[0])
    
    for wid, slot_info in wid_to_slot.items():
        if slot_info.get('addr_mode') == 'INDIRECT_STACK':
            # 如果这个WID是数组写入，跳过（由数组恢复处理，但全局数组需要重新计算R12）
            if wid in array_write_wids:
                print(f"    [R12恢复] 跳过 {wid}：已标记为数组写入，R12将从栈重新计算")
                continue
            addr_slot = slot_info.get('addr_slot_symbol')
            if addr_slot:
                wid_num = int(wid[1:])
                indirect_stack_wids.append((wid_num, wid, addr_slot))
    indirect_stack_wids.sort(key=lambda x: x[0])
    
    code_lines = [
        "",
        "; ===== R12寄存器恢复（基于INDIRECT_STACK WID） =====",
        "_restore_reg12:",
        "    ; 获取当前WID",
        "    MOV.W &ASAP_WID_SAVE, R13    ; R13 = 当前WID",
    ]
    
    # 为每个INDIRECT_STACK WID范围生成R12恢复代码
    if indirect_stack_wids:
        # 找出所有使用相同addr_slot的WID范围
        addr_slot_groups = {}
        for wid_num, wid, addr_slot in indirect_stack_wids:
            if addr_slot not in addr_slot_groups:
                addr_slot_groups[addr_slot] = []
            addr_slot_groups[addr_slot].append(wid_num)
        
        for addr_slot, wid_nums in addr_slot_groups.items():
            min_wid = min(wid_nums)
            max_wid = max(wid_nums)
            code_lines.extend([
                f"    ; 检查WID {min_wid}-{max_wid} 范围",
                f"    CMP.W #{min_wid}, R13",
                f"    JL _skip_r12_{addr_slot.replace('__ADDR_', '')}",
                f"    CMP.W #{max_wid + 1}, R13",
                f"    JGE _skip_r12_{addr_slot.replace('__ADDR_', '')}",
                f"    ; ★★★ 恢复R12 = {addr_slot} ★★★",
                f"    MOV.W &{addr_slot}, R12",
                f"_skip_r12_{addr_slot.replace('__ADDR_', '')}:",
            ])
    
    # 【关键修复】为全局数组写入的WID生成R12恢复代码（从栈重新计算）
    # 需要区分两种情况：
    # 1. 全局数组（is_global=true）：R12 = #array_name + index * element_size
    # 2. 参数传递数组：R12 = @SP + index * element_size
    if global_array_write_wids:
        code_lines.extend([
            "",
            "    ; ===== 全局数组写入WID的R12恢复（从栈重新计算）=====",
        ])
        
        # 按数组分组
        array_groups = {}
        for wid_num, wid, array_name, logical_addr in global_array_write_wids:
            if array_name not in array_groups:
                array_groups[array_name] = []
            array_groups[array_name].append((wid_num, wid, logical_addr))
        
        # 【辅助函数】从candidates中找到数组写入函数中的循环计数器偏移
        def find_index_offset(array_name, callee_funcs):
            """从candidates中查找循环计数器的栈偏移"""
            if not candidates or not callee_funcs:
                return 2  # 默认偏移
            
            # 在写入函数中查找 ADD.W #1 操作（通常是 i++ 或 dividend++）
            for wid, info in candidates.items():
                func = info.get('function', '')
                if func in callee_funcs:
                    mnemonic = info.get('mnemonic', '')
                    src = info.get('src', '')
                    dst = info.get('dst', '')
                    # 查找 ADD.W #1, X(R1) 模式（循环计数器 ++）
                    if 'ADD' in mnemonic and src == '#1' and '(R1)' in dst:
                        # 提取栈偏移，如 "2(R1)" -> 2
                        import re
                        match = re.match(r'(\d+)\(R1\)', dst)
                        if match:
                            return int(match.group(1))
            return 2  # 默认偏移
        
        for array_name, wid_list in array_groups.items():
            min_wid = min(w[0] for w in wid_list)
            max_wid = max(w[0] for w in wid_list)
            
            # 获取数组信息
            array_info = arrays_info.get(array_name, {})
            is_global = array_info.get('is_global', False)
            element_size = array_mirrors.get(array_name, {}).get('element_size', 4)
            callee_funcs = array_info.get('callee_funcs', [])
            
            # 查找循环计数器的栈偏移
            index_offset = find_index_offset(array_name, callee_funcs)
            
            # 计算RLAM移位量（element_size的log2）
            shift_count = {1: 0, 2: 1, 4: 2, 8: 3}.get(element_size, 2)
            
            if is_global:
                # 全局数组：R12 = #array_name + index * element_size
                code_lines.extend([
                    f"    ; 检查WID {min_wid}-{max_wid} 范围（{array_name}数组写入）",
                    f"    CMP.W #{min_wid}, R13",
                    f"    JL _skip_r12_recalc_{array_name}",
                    f"    CMP.W #{max_wid + 1}, R13",
                    f"    JGE _skip_r12_recalc_{array_name}",
                    f"    ; ★★★ 从栈重新计算R12（{array_name} - 全局数组）★★★",
                    f"    ; R12 = #{array_name} + index * {element_size}",
                    f"    ; 【关键】使用ASAP_SP_SAVE而不是R1，因为此时SP还没恢复",
                    f"    MOV.W &ASAP_SP_SAVE, R8     ; R8 = 恢复的SP（临时）",
                    f"    MOV.W {index_offset}(R8), R12 ; R12 = index（从SP+{index_offset}读取）",
                ])
                if shift_count > 0:
                    code_lines.append(f"    RLAM.W #{shift_count}, R12      ; R12 = index * {element_size}")
                code_lines.extend([
                    f"    ADD.W #{array_name}, R12    ; R12 = #{array_name} + index * {element_size}",
                    f"_skip_r12_recalc_{array_name}:",
                ])
            else:
                # 参数传递数组：R12 = @SP + index * element_size
                code_lines.extend([
                    f"    ; 检查WID {min_wid}-{max_wid} 范围（{array_name}数组写入）",
                    f"    CMP.W #{min_wid}, R13",
                    f"    JL _skip_r12_recalc_{array_name}",
                    f"    CMP.W #{max_wid + 1}, R13",
                    f"    JGE _skip_r12_recalc_{array_name}",
                    f"    ; ★★★ 从栈重新计算R12（{array_name} - 参数传递数组）★★★",
                    f"    ; R12 = @SP + index * {element_size}",
                    f"    ; 【关键】使用ASAP_SP_SAVE而不是R1，因为此时SP还没恢复",
                    f"    MOV.W &ASAP_SP_SAVE, R8     ; R8 = 恢复的SP（临时）",
                    f"    MOV.W {index_offset}(R8), R12 ; R12 = index（从SP+{index_offset}读取）",
                ])
                if shift_count > 0:
                    code_lines.append(f"    RLAM.W #{shift_count}, R12      ; R12 = index * {element_size}")
                code_lines.extend([
                    f"    ADD.W @R8, R12              ; R12 = @SP + index * {element_size}",
                    f"_skip_r12_recalc_{array_name}:",
                ])
    
    code_lines.extend([
        "",
        "; ===== 循环数组恢复 =====",
        "_restore_arrays:",
    ])
    
    for array_name, config in array_mirrors.items():
        mirror_symbol = config['mirror_symbol']
        base_symbol = base_slots.get(array_name, {}).get('symbol')
        size = config['size']
        element_size = config['element_size']
        total_bytes = config['total_bytes']
        
        # 获取param_reg（用于间接寻址的寄存器）
        array_info = arrays_info.get(array_name, {})
        param_reg = array_info.get('param_reg', 'R12')
        is_passed_as_param = array_info.get('passed_as_param', False)
        
        # 获取该数组的WID范围
        wid_list = array_wid_ranges.get(array_name, [])
        if wid_list:
            min_wid = min(wid_list)
            max_wid = max(wid_list)
            wid_range_comment = f"WID {min_wid}-{max_wid}"
        else:
            min_wid = 0
            max_wid = 999
            wid_range_comment = "所有WID"
        
        # ====== 类型1: 通过参数传递的数组（INDIRECT_STACK）======
        if base_symbol and is_passed_as_param:
            code_lines.extend([
                f"    ; ----- 恢复 {array_name}[{size}] ({total_bytes}字节) [INDIRECT_STACK] -----",
                f"    ; WID范围: {wid_range_comment}",
                f"    ; 恢复策略:",
                f"    ;   WID < {min_wid}: 跳过（数组还未开始写入）",
                f"    ;   WID >= {min_wid}: 完整恢复（数组可能正在写入或已完成，后续代码可能读取）",
                f"    ;   额外检查: 基地址必须 >= 当前SP（防止旧值导致错误恢复）",
            ])
            
            # WID范围检查：只有WID < min_wid时跳过
            # WID >= min_wid时都需要恢复（包括写入完成后被读取的情况）
            if wid_list:
                code_lines.extend([
                    f"    CMP.W #{min_wid}, R13",
                    f"    JL _skip_{array_name}       ; WID < {min_wid}，数组还没开始写，跳过",
                ])
            
            code_lines.extend([
                f"    ; 从 {mirror_symbol} 复制到 &{base_symbol} 指向的地址",
                f"    MOV.W &{base_symbol}, R10    ; R10 = 数组基地址",
                f"    CMP.W #0, R10",
                f"    JEQ _skip_{array_name}       ; 基地址为0，跳过",
                f"    ; 【关键检查】基地址必须 >= 当前SP（数组在调用者栈上，地址应该更高）",
                f"    MOV.W &ASAP_SP_SAVE, R11     ; R11 = 断电时的SP",
                f"    CMP.W R11, R10               ; 比较 base vs SP",
                f"    JLO _skip_{array_name}       ; base < SP，说明是旧值或无效，跳过",
                f"    ; 检查基地址是否在SRAM范围内",
                f"    CMP.W #0x2400, R10",
                f"    JHS _skip_{array_name}       ; 超出SRAM范围",
                f"    CMP.W #0x1C00, R10",
                f"    JLO _skip_{array_name}       ; 低于SRAM起始",
                f"    ; 复制镜像数据到原数组",
                f"    MOV.W &{base_symbol}, R10    ; R10 = 数组基地址（重新加载）",
                f"    MOV.W #{mirror_symbol}, R11  ; R11 = 镜像基地址",
                f"    MOV.W #{total_bytes}, R14    ; R14 = 字节数",
                f"_copy_{array_name}:",
                f"    MOV.W @R11+, 0(R10)          ; 复制2字节",
                f"    ADD.W #2, R10",
                f"    SUB.W #2, R14",
                f"    JNZ _copy_{array_name}",
                f"_skip_{array_name}:",
                f"",
            ])
        
        # ====== 类型2: 直接栈访问的数组（conv类型）======
        elif array_name in array_stack_info:
            stack_info = array_stack_info[array_name]
            stack_offset = stack_info['stack_offset']
            
            # 获取该数组所有WID对应的index_location
            wid_index_list = array_wid_index_map.get(array_name, [])
            wid_index_list.sort(key=lambda x: x[0])  # 按WID排序
            
            # 按index_location分组
            index_groups = {}
            for wid_num, idx_loc in wid_index_list:
                if idx_loc not in index_groups:
                    index_groups[idx_loc] = []
                index_groups[idx_loc].append(wid_num)
            
            code_lines.extend([
                f"    ; ----- 恢复 {array_name}[{size}] ({total_bytes}字节) [直接栈访问] -----",
                f"    ; WID范围: {wid_range_comment}",
                f"    ; 栈偏移: {stack_offset}",
                f"    ; 恢复策略:",
                f"    ;   WID < {min_wid}: 跳过（数组还未开始写入）",
                f"    ;   WID {min_wid}-{max_wid}: 增量恢复（正在写入）",
                f"    ;   WID > {max_wid}: 完整恢复（写入已完成，但后续代码可能读取）",
            ])
            
            # WID范围检查：只有WID < min_wid时跳过
            if wid_list:
                code_lines.extend([
                    f"    CMP.W #{min_wid}, R13",
                    f"    JL _skip_{array_name}       ; WID < {min_wid}，数组还没开始写，跳过",
                ])
            
            # 检查是否需要完整恢复（WID > max_wid）
            code_lines.extend([
                f"    ; 检查是否需要完整恢复（WID > {max_wid}，写入已完成）",
                f"    CMP.W #{max_wid + 1}, R13",
                f"    JGE _full_restore_{array_name}  ; WID > {max_wid}，完整恢复",
            ])
            
            # 增量恢复部分：根据当前循环索引恢复
            code_lines.append(f"    ; --- 增量恢复（WID {min_wid}-{max_wid}）---")
            
            # 如果只有一个index_location，使用简单逻辑
            if len(index_groups) == 1:
                index_location = list(index_groups.keys())[0]
                code_lines.append(f"    ; 索引变量: {index_location}")
                
                code_lines.extend([
                    f"    ; 读取当前循环变量i（已被标量恢复恢复）",
                    f"    MOV.W {index_location}, R15   ; R15 = 当前i值",
                ])
            else:
                # 多个index_location：根据WID范围选择正确的索引变量
                code_lines.append(f"    ; 多个循环使用不同索引变量，根据WID选择")
                
                # 为每个index_location生成条件分支
                for idx, (idx_loc, wid_nums) in enumerate(sorted(index_groups.items(), key=lambda x: min(x[1]))):
                    group_min = min(wid_nums)
                    group_max = max(wid_nums)
                    label_suffix = f"{array_name}_idx{idx}"
                    
                    code_lines.extend([
                        f"    ; 检查WID {group_min}-{group_max}，使用索引 {idx_loc}",
                        f"    CMP.W #{group_min}, R13",
                        f"    JL _check_idx_{label_suffix}",
                        f"    CMP.W #{group_max + 1}, R13",
                        f"    JGE _check_idx_{label_suffix}",
                        f"    MOV.W {idx_loc}, R15        ; R15 = 当前i值 (来自 {idx_loc})",
                        f"    JMP _idx_selected_{array_name}",
                        f"_check_idx_{label_suffix}:",
                    ])
                
                # 默认情况（不应该到达，但为安全起见）
                default_idx_loc = list(index_groups.keys())[0]
                code_lines.extend([
                    f"    MOV.W {default_idx_loc}, R15   ; 默认使用第一个索引",
                    f"_idx_selected_{array_name}:",
                ])
            
            # 增量恢复：只恢复已写入部分（0到当前循环索引i）
            code_lines.extend([
                f"    CMP.W #0, R15",
                f"    JZ _skip_{array_name}         ; i=0，跳过",
                f"    ; 限制恢复范围（防止越界）",
                f"    CMP.W #{size}, R15",
                f"    JLO _idx_ok_{array_name}",
                f"    MOV.W #{size}, R15            ; 限制为数组大小",
                f"_idx_ok_{array_name}:",
                f"    JMP _do_restore_{array_name}",
            ])
            
            # 完整恢复部分：恢复整个数组
            code_lines.extend([
                f"_full_restore_{array_name}:",
                f"    ; --- 完整恢复（WID > {max_wid}，数组写入已完成但后续需要读取）---",
                f"    MOV.W #{size}, R15            ; R15 = 数组大小（恢复全部）",
            ])
            
            # 恢复循环（增量和完整共用）
            # 对于is_stack_direct数组，使用__backup_xxx_start符号（由stage4/stage5生成）
            # 而不是__MIRROR_xxx符号（由stage4b生成）
            backup_symbol = f"__backup_{array_name}_start"
            
            code_lines.extend([
                f"_do_restore_{array_name}:",
                f"    ; 恢复循环（使用{backup_symbol}）",
                f"    MOV.W #0, R12                 ; R12 = 循环计数器",
                f"_restore_loop_{array_name}:",
                f"    MOV.W R12, R10",
                f"    RLAM.W #1, R10                ; R10 = idx*2",
                f"    ; 源地址: backup[idx]",
                f"    MOV.W #{backup_symbol}, R11",
                f"    ADD.W R10, R11                ; R11 = backup_base + idx*2",
                f"    ; 目标地址: array[idx] (SP+{stack_offset}+idx*2)",
                f"    MOV.W #{stack_offset}, R14",
                f"    ADD.W R1, R14                 ; R14 = SP + {stack_offset}",
                f"    ADD.W R10, R14                ; R14 += idx*2",
                f"    ; 恢复一个元素",
                f"    MOV.W @R11, 0(R14)            ; array[idx] = backup[idx]",
                f"    ; 下一个",
                f"    ADD.W #1, R12",
                f"    CMP.W R12, R15                ; 比较 idx 和 恢复数量",
                f"    JNE _restore_loop_{array_name}",
                f"_skip_{array_name}:",
                f"",
            ])
        
        # ====== 类型3: 全局数组（如crcTable, filter）======
        elif array_info.get('is_global', False):
            # 全局数组直接使用数组名作为目标地址
            
            # 【CF专用修复】检测SRAM全局数组（如filter）
            # SRAM地址范围: 0x1C00 - 0x2400
            # 这类数组断电后数据完全丢失，必须始终恢复
            # 检测方法：检查数组名是否在SRAM全局数组列表中
            sram_global_arrays = ['filter', 'model']  # SRAM全局数组：CF的filter, AR的model
            is_sram_global = array_name in sram_global_arrays
            
            # 【修改】使用数组所在函数的第一个WID作为恢复条件，而不是数组写入的第一个WID
            # 这样只要进入了该函数，就会恢复数组（避免在函数执行过程中断电后无法恢复）
            callee_funcs = array_info.get('callee_funcs', [])
            func_start_wid = min_wid  # 默认使用数组写入的第一个WID
            if callee_funcs and func_first_wid:
                # 找到写入该数组的函数的第一个WID
                for func in callee_funcs:
                    if func in func_first_wid:
                        func_wid = func_first_wid[func]
                        if func_wid < func_start_wid:
                            func_start_wid = func_wid
                            print(f"    [全局数组恢复] {array_name}: 使用函数 {func} 的第一个WID {func_wid} 作为恢复条件（原数组写入WID: {min_wid}）")
            
            # 【CF专用】如果是SRAM全局数组，始终恢复，不检查WID
            if is_sram_global:
                print(f"    [SRAM全局数组] {array_name}: 始终恢复（断电后SRAM数据丢失）")
                code_lines.extend([
                    f"    ; ----- 恢复 {array_name}[{size}] ({total_bytes}字节) [SRAM全局数组] -----",
                    f"    ; 【关键】SRAM全局数组，断电后数据完全丢失，始终恢复",
                    f"    ; 不检查WID条件，无论断电发生在哪个位置都必须恢复",
                ])
            else:
                code_lines.extend([
                    f"    ; ----- 恢复 {array_name}[{size}] ({total_bytes}字节) [全局数组] -----",
                    f"    ; 数组写入WID范围: {wid_range_comment}",
                    f"    ; 恢复条件: WID >= {func_start_wid}（进入写入函数即恢复）",
                    f"    ; 恢复策略:",
                    f"    ;   WID < {func_start_wid}: 跳过（还未进入写入函数）",
                    f"    ;   WID >= {func_start_wid}: 完整恢复（函数正在执行或已完成）",
                ])
                
                # WID范围检查：仅对非SRAM全局数组使用
                if wid_list:
                    code_lines.extend([
                        f"    CMP.W #{func_start_wid}, R13",
                        f"    JL _skip_{array_name}       ; WID < {func_start_wid}，还未进入写入函数，跳过",
                    ])
            
            code_lines.extend([
                f"    ; 从 {mirror_symbol} 复制到 {array_name}",
                f"    MOV.W #{array_name}, R10      ; R10 = 全局数组地址",
                f"    MOV.W #{mirror_symbol}, R11   ; R11 = 镜像基地址",
                f"    MOV.W #{total_bytes}, R14     ; R14 = 字节数",
                f"_copy_{array_name}:",
                f"    MOV.W @R11+, 0(R10)           ; 复制2字节",
                f"    ADD.W #2, R10",
                f"    SUB.W #2, R14",
                f"    JNZ _copy_{array_name}",
                f"_skip_{array_name}:",
                f"",
            ])
        
        else:
            code_lines.append(f"    ; 跳过 {array_name}: 无法确定恢复方式")
    
    return '\n'.join(code_lines)


def main():
    parser = argparse.ArgumentParser(description='Stage 11b: 数组恢复代码')
    parser.add_argument('--restore', default='build/asap_restore.s', help='恢复代码文件')
    parser.add_argument('--loop-arrays', default='build/loop_arrays.json', help='循环数组信息')
    parser.add_argument('--fram-slots', default='build/fram_slots.json', help='FRAM槽位')
    parser.add_argument('--candidates', default='build/candidates.json', help='候选写入信息（用于直接栈访问数组）')
    
    args = parser.parse_args()
    
    print("Stage 11b: 注入循环数组恢复代码...")
    
    inject_array_restore(args.restore, args.loop_arrays, args.fram_slots, args.candidates)


if __name__ == '__main__':
    main()


