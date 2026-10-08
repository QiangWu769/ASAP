#!/usr/bin/env python3
"""
Stage 3 Array: 识别关键写（包括数组索引感知）
输入: build/A_sym.s, build/function_info.json, Compiler/bc_core_config.json
输出: build/candidates.json（新增type=array字段）
"""
import argparse
import json
import re

def load_config(config_file):
    """加载配置文件"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  ⚠ 配置文件未找到: {config_file}")
        return {"exclude_functions": [], "exclude_peripherals": []}

def is_peripheral_write(dst, exclude_peripherals):
    """检查是否是外设写入"""
    addr_match = re.search(r'&?(0x[0-9A-Fa-f]+)', dst)
    if addr_match:
        addr = addr_match.group(1).upper()
        return addr in [p.upper() for p in exclude_peripherals]
    return False

def detect_array_pattern(lines, start_idx, dst):
    """
    检测数组写入模式
    特征：
    1. 地址通过多条指令计算（RLAM, ADD等）
    2. 使用循环变量作为索引
    3. 在循环标签内
    
    返回：{
        'is_array': True/False,
        'index_location': 'offset(R1)',  # 索引变量的栈位置
        'array_base': 'vec' 或 'out' 等，精确识别
        'stack_offset': 实际的栈偏移（如1002）
    }
    """
    result = {'is_array': False}
    
    # 向上追溯5-10行，查找地址计算过程
    lookback = 10
    start = max(0, start_idx - lookback)
    context_lines = lines[start:start_idx + 1]
    
    # 检测特征1：是否有RLAM指令（左移 = *2，数组索引计算）
    has_shift = any('RLAM' in line for line in context_lines)
    
    # 检测特征2：是否在循环内（查找上方有.L标签）
    # 匹配所有.L开头的标签（包括.L1:, .LBE6:, .LFB0:等）
    in_loop = False
    loop_label = None
    for line in reversed(context_lines):
        stripped = line.strip()
        # 匹配 .Lxxx: 格式（.L后跟任意字符，以:结尾）
        if re.match(r'^\.L\w*:', stripped):
            in_loop = True
            loop_label = stripped[:-1]  # 移除冒号
            break
    
    # 检测特征3：地址计算是否读取栈变量（可能是循环索引i）
    index_var = None
    for line in context_lines:
        # 查找 MOV.W offset(R1), Rx 模式
        match = re.search(r'MOV\.W\s+(\d+)\(R1\),\s+R\d+', line)
        if match:
            index_var = f"{match.group(1)}(R1)"
    
    # 检测特征4：计算最终的栈偏移
    # 查找模式：MOV #2012 + ADD R1 + ADD #-1010 → 最终偏移 = 2012-1010 = 1002
    stack_offset = None
    base_const = None
    adjust_const = None
    
    for line in context_lines:
        # MOV.W #2012, Rx
        match = re.search(r'MOV\.W\s+#(\d+),\s+R\d+', line)
        if match:
            base_const = int(match.group(1))
        # ADD.W #-1010, Rx 或 ADD.W #1010, Rx
        match = re.search(r'ADD\.W\s+#(-?\d+),\s+R\d+', line)
        if match:
            adjust_const = int(match.group(1))
    
    if base_const is not None and adjust_const is not None:
        stack_offset = base_const + adjust_const
    
    # 检测特征5：全局数组符号
    array_base = None
    for line in context_lines:
        # 全局数组：ADD.W #vec, R12
        match = re.search(r'ADD\.W\s+#(\w+),\s+R\d+', line)
        if match and match.group(1) not in ['0', '1']:  # 排除数字
            array_base = match.group(1)
            break
    
    # 局部数组命名：根据栈偏移+循环标签区分
    if not array_base and stack_offset is not None:
        # 根据栈偏移给数组命名
        # out在低地址（SP+0），vec在高地址（SP+962）
        if stack_offset >= 500:
            array_base = f"vec_sp{stack_offset}"  # vec在高地址
        elif stack_offset >= 0:
            array_base = f"out_sp{stack_offset}"  # out在低地址
        else:
            array_base = f"array_sp{abs(stack_offset)}"
    
    # 综合判断是否是数组写入
    if has_shift and in_loop and index_var:
        result = {
            'is_array': True,
            'index_location': index_var,
            'array_base': array_base or 'computed',
            'loop_label': loop_label,
            'stack_offset': stack_offset
        }
    
    return result

def trace_register_source(func_name, reg, call_info):
    """
    追踪寄存器的来源，判断是否来自栈地址参数
    
    Args:
        func_name: 当前函数名
        reg: 寄存器名 (如 'R12')
        call_info: 调用信息（包含参数传递信息）
    
    Returns:
        如果寄存器来自栈地址，返回栈地址信息；否则返回None
    """
    if not call_info or 'function_params' not in call_info:
        return None
    
    # 查找这个函数的参数信息
    func_params = call_info['function_params'].get(func_name, [])
    
    for param in func_params:
        if param['reg'] == reg:
            # 检查是否是栈地址类型的参数
            if param['type'] in ['stack_address', 'stack_pointer']:
                return {
                    'type': 'stack_derived',
                    'reg': reg,
                    'source_func': param.get('source_func'),
                    'source_offset': param.get('offset', 0),
                    'original_addr': param.get('logical_addr', f"{param.get('source_func')}::SP+{param.get('offset', 0)}")
                }
    
    return None

def analyze_writes(asm_file, function_info, config, enable_array_detection=True, call_info=None):
    """分析关键写操作（支持数组检测和间接栈写入检测）"""
    candidates = {}
    wid_counter = 1
    current_func = None
    
    exclude_funcs = set(f.lower() for f in config.get('exclude_functions', []))
    
    # 提取外设地址
    exclude_peripherals = []
    peripheral_dict = config.get('exclude_peripherals', {})
    for category, regs in peripheral_dict.items():
        if isinstance(regs, dict):
            for reg_name, addr in regs.items():
                if isinstance(addr, str) and addr.startswith('0x'):
                    exclude_peripherals.append(addr)
    
    prologue_filtered = 0
    epilogue_filtered = 0
    array_detected = 0
    indirect_stack_writes = 0  # 新增：间接栈写入计数
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 构建函数行号映射
    func_line_map = {}
    for func_name, info in function_info.items():
        start = info['start_line']
        end = info.get('end_line', start + 100)
        for line_num in range(start, end + 1):
            func_line_map[line_num] = func_name
    
    in_prologue = False
    in_epilogue = False
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # 检测 prologue/epilogue 边界
        if '; start of function' in stripped:
            in_prologue = True
            in_epilogue = False
        elif '; start of prologue' in stripped:
            in_prologue = True
        elif '; end of prologue' in stripped:
            in_prologue = False
        elif '; start of epilogue' in stripped:
            in_epilogue = True
            in_prologue = False
        elif '; end of epilogue' in stripped:
            in_epilogue = False
        
        current_func = func_line_map.get(i, current_func)
        
        if current_func and current_func.lower() in exclude_funcs:
            continue
        
        skip_prologue_epilogue = in_prologue or in_epilogue
        
        # 处理复合指令
        instructions_to_process = []
        if '{' in stripped:
            sub_instructions = stripped.split('{')
            for sub_instr in sub_instructions:
                sub_instr = sub_instr.strip()
                if sub_instr:
                    instructions_to_process.append(sub_instr)
        else:
            instructions_to_process.append(stripped)
        
        for instr_str in instructions_to_process:
            instr_match = re.match(r'(MOV|ADD|SUB|AND|OR|XOR|BIS|BIC|ADDC|SUBC|INC|DEC)(?:\.([WB]))?\s+(.+)', instr_str, re.IGNORECASE)
            if not instr_match:
                continue
            
            instr = instr_match.group(1).upper()
            width = instr_match.group(2) if instr_match.group(2) else 'W'
            operands = instr_match.group(3).strip()
            
            if ',' in operands:
                parts = operands.rsplit(',', 1)
                src = parts[0].strip()
                dst = parts[1].strip()
            else:
                src = None
                dst = operands.strip()
            
            # 跳过寄存器到寄存器
            if dst.upper().startswith('R') and len(dst) <= 3:
                continue
            
            # 跳过外设写入
            if is_peripheral_write(dst, exclude_peripherals):
                continue
            
            addr_mode = None
            base_reg = None
            offset = 0
            logical_addr = None
            
            # 绝对地址（数字形式）
            if re.match(r'&?0x[0-9A-Fa-f]+', dst):
                addr_match = re.search(r'(0x[0-9A-Fa-f]+)', dst)
                addr_val = int(addr_match.group(1), 16)
                logical_addr = addr_match.group(1).upper()
                
                # 检查是否在SRAM范围内 (0x1C00-0x2400)
                if 0x1C00 <= addr_val < 0x2400:
                    addr_mode = 'SRAM_GLOBAL'
                    logical_addr = f"SRAM::{logical_addr}"
                else:
                    addr_mode = 'ABSOLUTE'
            
            # 符号形式的全局变量（如 &count, &seed）
            # 匹配 &symbol 但排除寄存器和外设
            elif re.match(r'&([a-zA-Z_][a-zA-Z0-9_]*)\s*$', dst):
                symbol_match = re.match(r'&([a-zA-Z_][a-zA-Z0-9_]*)\s*$', dst)
                symbol_name = symbol_match.group(1)
                # 排除外设寄存器（通常全大写或特定前缀）
                if not (symbol_name.isupper() or 
                        symbol_name.startswith('UC') or 
                        symbol_name.startswith('PM') or
                        symbol_name.startswith('WDT') or
                        symbol_name.startswith('CS') or
                        symbol_name in ['ASAP_WID_SAVE', 'ASAP_SP_SAVE', 'ASAP_PC_SAVE']):
                    addr_mode = 'SRAM_GLOBAL'
                    logical_addr = f"SRAM::{symbol_name}"
            
            # 索引寻址
            elif re.match(r'([0-9]+)\(R([0-9]+)\)', dst):
                idx_match = re.match(r'([0-9]+)\(R([0-9]+)\)', dst)
                offset = int(idx_match.group(1))
                base_reg = f"R{idx_match.group(2)}"
                addr_mode = 'INDEXED'
                
                if base_reg == 'R1' or dst.endswith('(SP)'):
                    logical_addr = f"{current_func}::SP+{offset}"
                else:
                    # 检查是否是间接栈写入
                    reg_source = trace_register_source(current_func, base_reg, call_info)
                    if reg_source and reg_source['type'] == 'stack_derived':
                        # 这是间接栈写入！
                        addr_mode = 'INDIRECT_STACK'
                        logical_addr = f"{reg_source['source_func']}::SP+{reg_source['source_offset']}+{offset}"
                        indirect_stack_writes += 1
                    else:
                        logical_addr = f"{current_func}::{base_reg}+{offset}"
            
            # 寄存器间接
            elif re.match(r'@R([0-9]+)', dst):
                reg_match = re.match(r'@R([0-9]+)', dst)
                base_reg = f"R{reg_match.group(1)}"
                addr_mode = 'INDIRECT'
                offset = 0
                
                if base_reg == 'R1':
                    logical_addr = f"{current_func}::SP+0"
                else:
                    # 检查是否是间接栈写入
                    reg_source = trace_register_source(current_func, base_reg, call_info)
                    if reg_source and reg_source['type'] == 'stack_derived':
                        # 这是间接栈写入！
                        addr_mode = 'INDIRECT_STACK'
                        logical_addr = f"{reg_source['source_func']}::SP+{reg_source['source_offset']}"
                        indirect_stack_writes += 1
                    else:
                        logical_addr = f"{current_func}::{base_reg}+0"
            
            if addr_mode and logical_addr:
                if skip_prologue_epilogue:
                    if in_prologue:
                        prologue_filtered += 1
                    else:
                        epilogue_filtered += 1
                    continue
                
                # === 新增：数组检测 ===
                array_info = {'is_array': False}
                if enable_array_detection and addr_mode == 'INDIRECT':
                    array_info = detect_array_pattern(lines, i-1, dst)
                    if array_info['is_array']:
                        array_detected += 1
                
                wid = f"W{wid_counter:03d}"
                candidates[wid] = {
                    'line': i,
                    'function': current_func or 'unknown',
                    'mnemonic': f'{instr}.{width}',
                    'src': src,
                    'dst': dst,
                    'addr_mode': addr_mode,
                    'base_reg': base_reg,
                    'offset': offset,
                    'logical_addr': logical_addr,
                    # === 新增字段 ===
                    'type': 'array' if array_info['is_array'] else 'scalar',
                    'array_info': array_info if array_info['is_array'] else None
                }
                wid_counter += 1
    
    return candidates, prologue_filtered, epilogue_filtered, array_detected

def main():
    parser = argparse.ArgumentParser(description='Stage 3 Array: 识别关键写（含数组和间接栈写入）')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--call-info', default=None, help='调用信息JSON (可选，用于间接栈写入检测)')
    parser.add_argument('--config', default='Compiler/bc_core_config.json', help='配置文件')
    parser.add_argument('--output', default='build/candidates.json', help='输出JSON')
    parser.add_argument('--enable-array-detection', action='store_true', help='启用数组检测')
    
    args = parser.parse_args()
    
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    config = load_config(args.config)
    
    # 加载调用信息（用于间接栈写入检测）
    call_info = None
    if args.call_info:
        try:
            with open(args.call_info, 'r') as f:
                call_info = json.load(f)
            print(f"  ✓ 已加载调用信息: {args.call_info}")
        except FileNotFoundError:
            print(f"  ⚠ 调用信息文件未找到: {args.call_info}，跳过间接栈写入检测")
    
    candidates, prologue_filtered, epilogue_filtered, array_detected = analyze_writes(
        args.asm_file, function_info, config, args.enable_array_detection, call_info
    )
    
    with open(args.output, 'w') as f:
        json.dump(candidates, f, indent=2)
    
    # 统计间接栈写入
    indirect_count = sum(1 for c in candidates.values() if c.get('addr_mode') == 'INDIRECT_STACK')
    
    print(f"  ✓ 分析完成:")
    print(f"    - 识别到 {len(candidates)} 个关键写")
    if array_detected > 0:
        print(f"    - 其中数组写入: {array_detected} 个")
    if indirect_count > 0:
        print(f"    - 其中间接栈写入: {indirect_count} 个（通过指针参数）")
    if prologue_filtered > 0:
        print(f"    - 过滤prologue写操作: {prologue_filtered} 个")
    if epilogue_filtered > 0:
        print(f"    - 过滤epilogue写操作: {epilogue_filtered} 个")
    
    # 统计
    types = {'scalar': 0, 'array': 0}
    addr_modes = {}
    for wid, info in candidates.items():
        types[info['type']] = types.get(info['type'], 0) + 1
        mode = info.get('addr_mode', 'UNKNOWN')
        addr_modes[mode] = addr_modes.get(mode, 0) + 1
    
    print(f"  ✓ 类型分布:")
    for t, count in types.items():
        print(f"    {t}: {count}")
    
    if indirect_count > 0:
        print(f"  ✓ 寻址模式分布:")
        for mode, count in sorted(addr_modes.items()):
            print(f"    {mode}: {count}")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

