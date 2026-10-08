#!/usr/bin/env python3
"""
Stage 3: 识别关键写（排除输出相关和FRAM变量）
输入: build/A_sym.s, build/function_info.json, Compiler/bc_core_config.json, build/fram_variables.json
输出: build/candidates.json
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

def load_fram_variables(fram_file):
    """加载FRAM变量列表"""
    try:
        with open(fram_file, 'r') as f:
            data = json.load(f)
        
        # 构建快速查找结构
        fram_addrs = set()
        fram_ranges = []
        
        for var in data.get('fram_variables', []):
            try:
                addr = int(var['address'], 16)
                fram_addrs.add(addr)
                
                # 如果有大小信息，记录地址范围
                if var.get('size') != 'unknown' and var['size'] > 0:
                    fram_ranges.append((addr, addr + var['size']))
            except:
                continue
        
        # 添加已知的FRAM section范围
        for name, info in data.get('fram_sections', {}).items():
            fram_ranges.append((info['start'], info['end']))
        
        return {
            'addresses': fram_addrs,
            'ranges': fram_ranges
        }
    except FileNotFoundError:
        print(f"  ⚠ FRAM变量文件未找到: {fram_file}，跳过FRAM过滤")
        return {'addresses': set(), 'ranges': []}

def is_fram_address(addr, fram_info):
    """检查地址是否在FRAM区域"""
    # 检查精确地址
    if addr in fram_info['addresses']:
        return True
    
    # 检查地址范围
    for start, end in fram_info['ranges']:
        if start <= addr < end:
            return True
    
    return False

def is_peripheral_write(dst, exclude_peripherals):
    """检查是否是外设写入"""
    # 提取地址
    addr_match = re.search(r'&?(0x[0-9A-Fa-f]+)', dst)
    if addr_match:
        addr = addr_match.group(1).upper()
        return addr in [p.upper() for p in exclude_peripherals]
    return False

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

def analyze_writes(asm_file, function_info, config, fram_info=None, call_info=None):
    """分析关键写操作（排除FRAM变量，支持间接栈写入检测）"""
    candidates = {}
    wid_counter = 1
    current_func = None
    indirect_stack_writes = 0  # 统计间接栈写入数量
    
    exclude_funcs = set(f.lower() for f in config.get('exclude_functions', []))
    
    # 提取所有外设地址（从嵌套字典中）
    exclude_peripherals = []
    peripheral_dict = config.get('exclude_peripherals', {})
    for category, regs in peripheral_dict.items():
        if isinstance(regs, dict):
            for reg_name, addr in regs.items():
                if isinstance(addr, str) and addr.startswith('0x'):
                    exclude_peripherals.append(addr)
    
    # FRAM过滤统计
    fram_filtered = 0
    prologue_filtered = 0  # 统计prologue过滤的写操作
    epilogue_filtered = 0  # 统计epilogue过滤的写操作
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 构建函数行号映射
    func_line_map = {}
    for func_name, info in function_info.items():
        start = info['start_line']
        end = info.get('end_line')
        if end is None:
            end = start + 100  # 默认假设函数长度
        for line_num in range(start, end + 1):
            func_line_map[line_num] = func_name
    
    # 跟踪 prologue/epilogue 状态
    in_prologue = False
    in_epilogue = False
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # 检测 prologue/epilogue 边界
        # ⭐ 关键修复：函数开始时重置 epilogue 状态
        if '; start of function' in stripped:
            in_prologue = True
            in_epilogue = False  # 重置前一个函数的epilogue状态！
        elif '; start of prologue' in stripped:
            in_prologue = True
        elif '; end of prologue' in stripped:
            # ⭐⭐ 修复：prologue在"; end of prologue"时立即结束
            # 参数保存在prologue之后，应该被插桩！
            in_prologue = False
        elif '; start of epilogue' in stripped:
            in_epilogue = True
            in_prologue = False
        elif '; end of epilogue' in stripped:
            in_epilogue = False
        
        # 更新当前函数
        current_func = func_line_map.get(i, current_func)
        
        # 跳过排除的函数
        if current_func and current_func.lower() in exclude_funcs:
            continue
        
        # ⭐ 跳过 prologue/epilogue 的写操作（参数保存/恢复）
        # 但先不跳过，让后面的逻辑检测并计数
        skip_prologue_epilogue = in_prologue or in_epilogue
        
        # 处理复合指令（用{分隔的多条指令）
        # 例如: ADD #13, 32(R1) { ADDC #0, 34(R1)
        # 需要处理两部分！
        instructions_to_process = []
        if '{' in stripped:
            sub_instructions = stripped.split('{')
            for sub_instr in sub_instructions:
                sub_instr = sub_instr.strip()
                if sub_instr:
                    instructions_to_process.append(sub_instr)
        else:
            instructions_to_process.append(stripped)
        
        # 处理所有指令（包括复合指令的多个部分）
        for instr_str in instructions_to_process:
            # 匹配修改内存的指令 (MOV, ADD, SUB, AND, XOR, BIS, BIC等)
            # 格式: INSTR.W src, dst 或 INSTR src, dst (宽度可选，默认W)
            instr_match = re.match(r'(MOV|ADD|SUB|AND|OR|XOR|BIS|BIC|ADDC|SUBC|INC|DEC)(?:\.([WB]))?\s+(.+)', instr_str, re.IGNORECASE)
            if not instr_match:
                continue
            
            instr = instr_match.group(1).upper()
            width = instr_match.group(2) if instr_match.group(2) else 'W'  # 默认word
            operands = instr_match.group(3).strip()
            
            # 解析操作数
            if ',' in operands:
                # 双操作数指令: src, dst
                parts = operands.rsplit(',', 1)
                src = parts[0].strip()
                dst = parts[1].strip()
            else:
                # 单操作数指令: dst (如 INC, DEC)
                src = None
                dst = operands.strip()
            
            # 跳过寄存器到寄存器的操作
            if dst.upper().startswith('R') and len(dst) <= 3:
                continue
            
            # 跳过外设写入
            if is_peripheral_write(dst, exclude_peripherals):
                continue
            
            # 分析寻址模式
            addr_mode = None
            base_reg = None
            offset = 0
            logical_addr = None
            
            # 绝对地址: &0x1234 或 0x1234
            if re.match(r'&?0x[0-9A-Fa-f]+', dst):
                addr_mode = 'ABSOLUTE'
                addr_match = re.search(r'(0x[0-9A-Fa-f]+)', dst)
                logical_addr = addr_match.group(1).upper()
                
                # 【新增】检查是否是FRAM变量
                if fram_info:
                    try:
                        addr_val = int(logical_addr, 16)
                        if is_fram_address(addr_val, fram_info):
                            fram_filtered += 1
                            continue  # 跳过FRAM变量
                    except:
                        pass
            
            # 索引寻址: offset(Rn)
            elif re.match(r'([0-9]+)\(R([0-9]+)\)', dst):
                idx_match = re.match(r'([0-9]+)\(R([0-9]+)\)', dst)
                offset = int(idx_match.group(1))
                base_reg = f"R{idx_match.group(2)}"
                addr_mode = 'INDEXED'
                
                # 栈索引: offset(R1) 或 offset(SP)
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
            
            # 寄存器间接: @Rn
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
            
            # 如果识别到有效的写操作
            if addr_mode and logical_addr:
                # 过滤 prologue/epilogue 的写操作
                if skip_prologue_epilogue:
                    if in_prologue:
                        prologue_filtered += 1
                    else:
                        epilogue_filtered += 1
                    continue  # 跳过此写操作
                
                wid = f"W{wid_counter:03d}"
                candidates[wid] = {
                    'line': i,
                    'function': current_func or 'unknown',
                    'mnemonic': f'{instr}.{width}',  # 使用实际指令名
                    'src': src,
                    'dst': dst,
                    'addr_mode': addr_mode,
                    'base_reg': base_reg,
                    'offset': offset,
                    'logical_addr': logical_addr
                }
                wid_counter += 1
    
    return candidates, fram_filtered, prologue_filtered, epilogue_filtered

def main():
    parser = argparse.ArgumentParser(description='Stage 3: 识别关键写')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--call-info', default=None, help='调用信息JSON (可选，用于间接栈写入检测)')
    parser.add_argument('--config', default='Compiler/bc_core_config.json', help='配置文件')
    parser.add_argument('--fram-vars', default='build/fram_variables.json', help='FRAM变量JSON')
    parser.add_argument('--output', default='build/candidates.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载函数信息
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    # 加载配置
    config = load_config(args.config)
    
    # 加载FRAM变量
    fram_info = load_fram_variables(args.fram_vars)
    
    # 加载调用信息（用于间接栈写入检测）
    call_info = None
    if args.call_info:
        try:
            with open(args.call_info, 'r') as f:
                call_info = json.load(f)
            print(f"  ✓ 已加载调用信息: {args.call_info}")
        except FileNotFoundError:
            print(f"  ⚠ 调用信息文件未找到: {args.call_info}，跳过间接栈写入检测")
    
    # 分析写操作
    candidates, fram_filtered, prologue_filtered, epilogue_filtered = analyze_writes(args.asm_file, function_info, config, fram_info, call_info)
    
    # 输出结果
    with open(args.output, 'w') as f:
        json.dump(candidates, f, indent=2)
    
    # 统计间接栈写入
    indirect_count = sum(1 for c in candidates.values() if c.get('addr_mode') == 'INDIRECT_STACK')
    
    print(f"  ✓ 分析完成:")
    print(f"    - 识别到 {len(candidates)} 个关键写")
    if indirect_count > 0:
        print(f"    - 其中 {indirect_count} 个间接栈写入（通过指针参数）")
    print(f"    - 排除了输出相关写操作")
    if fram_filtered > 0:
        print(f"    - 过滤FRAM变量写入: {fram_filtered} 个")
    if prologue_filtered > 0:
        print(f"    - 过滤prologue写操作: {prologue_filtered} 个")
    if epilogue_filtered > 0:
        print(f"    - 过滤epilogue写操作: {epilogue_filtered} 个")
    
    # 统计
    addr_modes = {}
    for wid, info in candidates.items():
        mode = info['addr_mode']
        addr_modes[mode] = addr_modes.get(mode, 0) + 1
    
    print(f"  ✓ 寻址模式分布:")
    for mode, count in addr_modes.items():
        print(f"    {mode}: {count}")
    
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

