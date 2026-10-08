#!/usr/bin/env python3
"""
Stage 8: 分析读写操作
从汇编文件中提取所有读写操作及其PC地址
输入: build/A_sym.s, build/function_info.json
输出: build/reads_writes.json
"""
import argparse
import json
import re

def analyze_reads_writes(asm_file, function_info):
    """分析汇编中的读写操作"""
    
    writes = []
    reads = []
    
    # 构建函数行号映射
    func_line_map = {}
    for func_name, info in function_info.items():
        start = info['start_line']
        end = info.get('end_line')
        if end is None:
            continue  # 跳过没有结束行的函数
        for line_num in range(start, end + 1):
            func_line_map[line_num] = func_name
    
    with open(asm_file, 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        current_func = func_line_map.get(i, 'unknown')
        
        # 分析MOV指令
        mov_match = re.match(r'MOV\.([WB])\s+([^,]+),\s*(.+)', stripped, re.IGNORECASE)
        if mov_match:
            src = mov_match.group(2).strip()
            dst = mov_match.group(3).strip()
            
            # 检查目标操作数（写）
            write_info = parse_operand(dst, current_func, i)
            if write_info:
                writes.append(write_info)
            
            # 检查源操作数（读）
            read_info = parse_operand(src, current_func, i)
            if read_info:
                reads.append(read_info)
        
        # 分析其他可能的读操作（ADD, CMP, etc.）
        for instr in ['ADD', 'SUB', 'CMP', 'BIT', 'AND', 'OR', 'XOR']:
            instr_match = re.match(f'{instr}\\.([WB])\\s+([^,]+),\\s*(.+)', stripped, re.IGNORECASE)
            if instr_match:
                src = instr_match.group(2).strip()
                dst = instr_match.group(3).strip()
                
                # 源操作数是读
                read_info = parse_operand(src, current_func, i)
                if read_info:
                    reads.append(read_info)
                
                # 目标操作数是读（读-修改-写）
                read_info2 = parse_operand(dst, current_func, i)
                if read_info2:
                    reads.append(read_info2)
    
    return {'writes': writes, 'reads': reads}

def parse_operand(operand, func_name, line_num):
    """解析操作数，提取逻辑地址"""
    
    # 绝对地址: &0x1234
    if re.match(r'&?0x[0-9A-Fa-f]+', operand):
        addr_match = re.search(r'(0x[0-9A-Fa-f]+)', operand)
        return {
            'line': line_num,
            'function': func_name,
            'addr_mode': 'ABSOLUTE',
            'logical_addr': addr_match.group(1).upper()
        }
    
    # 索引寻址: offset(Rn)
    idx_match = re.match(r'([0-9]+)\(R([0-9]+)\)', operand)
    if idx_match:
        offset = int(idx_match.group(1))
        base_reg = f"R{idx_match.group(2)}"
        
        if base_reg == 'R1':
            logical_addr = f"{func_name}::SP+{offset}"
        else:
            logical_addr = f"{func_name}::{base_reg}+{offset}"
        
        return {
            'line': line_num,
            'function': func_name,
            'addr_mode': 'INDEXED',
            'offset': offset,
            'logical_addr': logical_addr
        }
    
    # 寄存器间接: @Rn
    reg_match = re.match(r'@R([0-9]+)', operand)
    if reg_match:
        base_reg = f"R{reg_match.group(1)}"
        
        if base_reg == 'R1':
            logical_addr = f"{func_name}::SP+0"
        else:
            logical_addr = f"{func_name}::{base_reg}+0"
        
        return {
            'line': line_num,
            'function': func_name,
            'addr_mode': 'INDIRECT',
            'offset': 0,
            'logical_addr': logical_addr
        }
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Stage 8: 分析读写操作')
    parser.add_argument('asm_file', help='汇编文件')
    parser.add_argument('--functions', required=True, help='函数信息JSON')
    parser.add_argument('--output', default='build/reads_writes.json', help='输出JSON')
    
    args = parser.parse_args()
    
    # 加载函数信息
    with open(args.functions, 'r') as f:
        function_info = json.load(f)
    
    # 分析读写
    rw_data = analyze_reads_writes(args.asm_file, function_info)
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(rw_data, f, indent=2)
    
    print(f"  ✓ 分析读写操作:")
    print(f"    写操作: {len(rw_data['writes'])}")
    print(f"    读操作: {len(rw_data['reads'])}")
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()
