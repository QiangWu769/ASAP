#!/usr/bin/env python3
"""
Stage 3 v2: 识别关键写（排除输出相关和FRAM变量，支持寄存器追踪）
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
        fram_symbols = {}  # 符号名 -> 地址
        
        for var in data.get('fram_variables', []):
            try:
                addr = int(var['address'], 16)
                fram_addrs.add(addr)
                fram_symbols[var['name']] = addr
                
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
            'ranges': fram_ranges,
            'symbols': fram_symbols
        }
    except FileNotFoundError:
        print(f"  ⚠ FRAM变量文件未找到: {fram_file}，跳过FRAM过滤")
        return {'addresses': set(), 'ranges': [], 'symbols': {}}

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
    addr_match = re.search(r'&?(0x[0-9A-Fa-f]+)', dst)
    if addr_match:
        addr = addr_match.group(1).upper()
        return addr in [p.upper() for p in exclude_peripherals]
    return False

def trace_register_value(lines, line_idx, target_reg, max_lookback=50):
    """回溯追踪寄存器的值
    
    从line_idx向前扫描，找到target_reg最近的赋值
    返回：(value_type, value) 或 None
    
    value_type可以是：
    - 'immediate': 立即数
    - 'address': 地址
    - 'symbol': 符号
    - 'register': 另一个寄存器
    - 'unknown': 无法确定
    """
    
    target_reg_pattern = re.compile(rf'\b{target_reg}\b', re.IGNORECASE)
    
    for i in range(line_idx - 1, max(0, line_idx - max_lookback), -1):
        line = lines[i].strip()
        
        # 跳过注释和标签
        if line.startswith(';') or line.startswith('.') or line.endswith(':'):
            continue
        
        # 查找对目标寄存器的赋值
        # MOV src, Rn
        mov_match = re.match(r'MOV(?:\.([WB]))?\s+([^,]+),\s*(.+)', line, re.IGNORECASE)
        if mov_match:
            src = mov_match.group(2).strip()
            dst = mov_match.group(3).strip()
            
            # 检查是否是对目标寄存器的赋值
            if target_reg_pattern.match(dst):
                # 分析源操作数
                
                # 立即数: #1234 或 #0x1234
                if src.startswith('#'):
                    value_str = src[1:].strip()
                    try:
                        if value_str.startswith('0x'):
                            value = int(value_str, 16)
                        else:
                            value = int(value_str)
                        return ('immediate', value)
                    except:
                        return ('unknown', None)
                
                # 绝对地址: &0x1234 或 &symbol
                elif src.startswith('&'):
                    addr_str = src[1:].strip()
                    if addr_str.startswith('0x'):
                        try:
                            value = int(addr_str, 16)
                            return ('address', value)
                        except:
                            return ('unknown', None)
                    else:
                        # 符号地址
                        return ('symbol', addr_str)
                
                # 寄存器: R1, R12, etc.
                elif re.match(r'R\d+', src, re.IGNORECASE):
                    return ('register', src.upper())
                
                # 其他情况
                else:
                    return ('unknown', None)
        
        # ADD, SUB等修改寄存器的指令（不能确定最终值）
        if re.search(rf'(ADD|SUB|AND|OR|XOR|BIS|BIC).*,\s*{target_reg}\b', line, re.IGNORECASE):
            # 寄存器被修改但无法确定具体值
            return ('unknown', None)
    
    return None

def analyze_writes(asm_file, function_info, config, fram_info=None):
    """分析关键写操作（排除FRAM变量，支持寄存器追踪）"""
    candidates = {}
    wid_counter = 1
    current_func = None
    
    exclude_funcs = set(f.lower() for f in config.get('exclude_functions', []))
    
    # 提取所有外设地址
    exclude_peripherals = []
    peripheral_dict = config.get('exclude_peripherals', {})
    for category, regs in peripheral_dict.items():
        if isinstance(regs, dict):
            for reg_name, addr in regs.items():
                if isinstance(addr, str) and addr.startswith('0x'):
                    exclude_peripherals.append(addr)
    
    # FRAM过滤统计
    fram_filtered_direct = 0
    fram_filtered_indirect = 0
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    # 构建函数行号映射
    func_line_map = {}
    for func_name, info in function_info.items():
        start = info['start_line']
        end = info.get('end_line')
        if end is None:
            end = start + 100
        for line_num in range(start, end + 1):
            func_line_map[line_num] = func_name
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # 更新当前函数
        current_func = func_line_map.get(i, current_func)
        
        # 跳过排除的函数
        if current_func and current_func.lower() in exclude_funcs:
            continue
        
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
        
        # 处理所有指令
        for instr_str in instructions_to_process:
            # 匹配修改内存的指令
            instr_match = re.match(r'(MOV|ADD|SUB|AND|OR|XOR|BIS|BIC|ADDC|SUBC|INC|DEC)(?:\.([WB]))?\s+(.+)', instr_str, re.IGNORECASE)
            if not instr_match:
                continue
            
            instr = instr_match.group(1).upper()
            width = instr_match.group(2) if instr_match.group(2) else 'W'
            operands = instr_match.group(3).strip()
            
            # 解析操作数
            if ',' in operands:
                parts = operands.rsplit(',', 1)
                src = parts[0].strip()
                dst = parts[1].strip()
            else:
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
            should_skip = False
            
            # 绝对地址: &0x1234 或 0x1234
            if re.match(r'&?0x[0-9A-Fa-f]+', dst):
                addr_mode = 'ABSOLUTE'
                addr_match = re.search(r'(0x[0-9A-Fa-f]+)', dst)
                logical_addr = addr_match.group(1).upper()
                
                # 检查是否是FRAM变量
                if fram_info:
                    try:
                        addr_val = int(logical_addr, 16)
                        if is_fram_address(addr_val, fram_info):
                            fram_filtered_direct += 1
                            should_skip = True
                    except:
                        pass
            
            # 索引寻址: offset(Rn)
            elif re.match(r'([0-9]+)\(R([0-9]+)\)', dst):
                idx_match = re.match(r'([0-9]+)\(R([0-9]+)\)', dst)
                offset = int(idx_match.group(1))
                base_reg = f"R{idx_match.group(2)}"
                addr_mode = 'INDEXED'
                
                if base_reg == 'R1' or dst.endswith('(SP)'):
                    logical_addr = f"{current_func}::SP+{offset}"
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
                    logical_addr = f"{current_func}::{base_reg}+0"
                    
                    # 【关键】追踪寄存器的值，判断是否指向FRAM
                    if fram_info:
                        trace_result = trace_register_value(lines, i, base_reg)
                        
                        if trace_result:
                            value_type, value = trace_result
                            
                            if value_type == 'address' and isinstance(value, int):
                                # 寄存器被赋值为一个地址
                                if is_fram_address(value, fram_info):
                                    fram_filtered_indirect += 1
                                    should_skip = True
                            
                            elif value_type == 'symbol' and isinstance(value, str):
                                # 寄存器被赋值为一个符号（如&filter）
                                if value in fram_info['symbols']:
                                    fram_filtered_indirect += 1
                                    should_skip = True
            
            # 如果应该跳过，则不添加到candidates
            if should_skip:
                continue
            
            # 如果识别到有效的写操作
            if addr_mode and logical_addr:
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
                    'logical_addr': logical_addr
                }
                wid_counter += 1
    
    total_fram_filtered = fram_filtered_direct + fram_filtered_indirect
    return candidates, {
        'total': total_fram_filtered,
        'direct': fram_filtered_direct,
        'indirect': fram_filtered_indirect
    }

def main():
    parser = argparse.ArgumentParser(description='Stage 3 v2: 识别关键写（支持寄存器追踪）')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--config', default='Compiler/bc_core_config.json', help='配置文件')
    parser.add_argument('--fram-vars', default='build/fram_variables.json', help='FRAM变量JSON')
    parser.add_argument('--output', default='build/candidates.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载数据
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    config = load_config(args.config)
    fram_info = load_fram_variables(args.fram_vars)
    
    # 分析写操作
    candidates, fram_stats = analyze_writes(args.asm_file, function_info, config, fram_info)
    
    # 输出结果
    with open(args.output, 'w') as f:
        json.dump(candidates, f, indent=2)
    
    print(f"  ✓ 分析完成:")
    print(f"    - 识别到 {len(candidates)} 个关键写")
    print(f"    - 排除了输出相关写操作")
    
    if fram_stats['total'] > 0:
        print(f"    - 过滤FRAM变量写入: {fram_stats['total']} 个")
        print(f"      · 直接地址: {fram_stats['direct']} 个")
        print(f"      · 寄存器间接: {fram_stats['indirect']} 个")
    
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

























