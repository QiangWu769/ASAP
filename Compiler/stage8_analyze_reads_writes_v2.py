#!/usr/bin/env python3
"""
Stage 8 v2: 分析读写操作（从反汇编提取，带PC地址）
从.elf反汇编中提取所有读写操作及其精确PC地址
输入: firmware_temp.elf, build/function_info.json
输出: build/reads_writes.json
"""
import argparse
import json
import re
import subprocess

def disassemble_elf(elf_file):
    """反汇编.elf文件，获取带PC的指令"""
    result = subprocess.run(
        ['msp430-elf-objdump', '-d', elf_file],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise Exception(f"反汇编失败: {result.stderr}")
    
    return result.stdout.split('\n')

def get_function_addr_ranges(elf_file):
    """从符号表获取函数的地址范围"""
    result = subprocess.run(
        ['msp430-elf-nm', '-n', elf_file],
        capture_output=True,
        text=True
    )
    
    functions = {}
    lines = result.stdout.strip().split('\n')
    
    for line in lines:
        # 格式: 00009966 T _uart_print_uint
        match = re.match(r'([0-9a-f]+)\s+[Tt]\s+(\w+)', line)
        if match:
            addr = int(match.group(1), 16)
            name = match.group(2)
            functions[name] = {'start': addr}
    
    # 计算结束地址（下一个函数的起始地址）
    sorted_funcs = sorted(functions.items(), key=lambda x: x[1]['start'])
    for i in range(len(sorted_funcs) - 1):
        name, info = sorted_funcs[i]
        next_start = sorted_funcs[i + 1][1]['start']
        functions[name]['end'] = next_start - 1
    
    # 最后一个函数的结束地址估算
    if sorted_funcs:
        last_name = sorted_funcs[-1][0]
        functions[last_name]['end'] = functions[last_name]['start'] + 0x1000
    
    return functions

def find_function_for_pc(pc, func_ranges):
    """根据PC查找所属函数"""
    for func_name, ranges in func_ranges.items():
        if ranges['start'] <= pc <= ranges['end']:
            return func_name
    return 'unknown'

def analyze_reads_writes_from_disasm(disasm_lines, func_ranges):
    """从反汇编分析读写操作"""
    
    writes = []
    reads = []
    
    for line in disasm_lines:
        # 解析指令行: "    88f8:	82 41 00 65 	mov	r1,	&0x6500	;"
        # 格式: PC: 机器码 指令操作数 注释
        # 使用更宽松的匹配：PC后面是机器码和指令
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f\s]+)\s+(.+)', line, re.IGNORECASE)
        if not match:
            continue
        
        pc = int(match.group(1), 16)
        rest = match.group(3).strip()
        
        # 提取指令部分（去掉注释）
        instruction = rest.split(';')[0].strip()
        # 去掉多余的tab
        instruction = re.sub(r'\s+', ' ', instruction)
        
        # 跳过pushm/popm等栈操作
        if instruction.split()[0].lower() in ['pushm', 'popm', 'push', 'pop', 'call', 'calla', 'ret', 'reti', 'jmp', 'jz', 'jnz', 'jc', 'jnc', 'jlo', 'jhs']:
            continue
        
        # 找到所属函数
        func_name = find_function_for_pc(pc, func_ranges)
        if func_name == 'unknown':
            continue
        
        # 分析MOV指令
        mov_match = re.match(r'MOV\.[WB]\s+([^,]+),\s*(.+)', instruction, re.IGNORECASE)
        if mov_match:
            src = mov_match.group(1).strip()
            dst = mov_match.group(2).strip()
            
            # 检查目标操作数（写）
            write_info = parse_operand(dst, func_name, pc)
            if write_info:
                writes.append(write_info)
            
            # 检查源操作数（读）
            read_info = parse_operand(src, func_name, pc)
            if read_info:
                reads.append(read_info)
        
        # 分析其他指令（ADD, SUB, CMP等）
        for instr in ['ADD', 'SUB', 'CMP', 'BIT', 'AND', 'OR', 'XOR']:
            instr_match = re.match(f'{instr}\\.([WB])\\s+([^,]+),\\s*(.+)', instruction, re.IGNORECASE)
            if instr_match:
                src = instr_match.group(2).strip()
                dst = instr_match.group(3).strip()
                
                # 源操作数是读
                read_info = parse_operand(src, func_name, pc)
                if read_info:
                    reads.append(read_info)
                
                # 目标操作数也是读（读-修改-写）
                read_info2 = parse_operand(dst, func_name, pc)
                if read_info2:
                    reads.append(read_info2)
    
    return {'writes': writes, 'reads': reads}

def parse_operand(operand, func_name, pc):
    """解析操作数，提取逻辑地址"""
    
    # 清理操作数（移除注释等）
    operand = operand.split(';')[0].strip()
    operand = operand.split('#')[0].strip()  # 移除立即数前缀
    
    # 绝对地址: &0x1234 或 0x1234
    if re.match(r'&?0x[0-9A-Fa-f]+', operand):
        addr_match = re.search(r'(0x[0-9A-Fa-f]+)', operand)
        return {
            'pc': hex(pc),
            'function': func_name,
            'addr_mode': 'ABSOLUTE',
            'logical_addr': addr_match.group(1).upper()
        }
    
    # 索引寻址: offset(Rn)
    idx_match = re.match(r'(-?[0-9]+)\(r([0-9]+)\)', operand, re.IGNORECASE)
    if idx_match:
        offset = int(idx_match.group(1))
        reg_num = idx_match.group(2)
        base_reg = f"R{reg_num}"
        
        if base_reg == 'R1' or reg_num == '1':
            logical_addr = f"{func_name}::SP+{offset}"
        else:
            logical_addr = f"{func_name}::{base_reg}+{offset}"
        
        return {
            'pc': hex(pc),
            'function': func_name,
            'addr_mode': 'INDEXED',
            'offset': offset,
            'logical_addr': logical_addr
        }
    
    # 寄存器间接: @Rn
    reg_match = re.match(r'@r([0-9]+)', operand, re.IGNORECASE)
    if reg_match:
        reg_num = reg_match.group(1)
        base_reg = f"R{reg_num}"
        
        if base_reg == 'R1' or reg_num == '1':
            logical_addr = f"{func_name}::SP+0"
        else:
            logical_addr = f"{func_name}::{base_reg}+0"
        
        return {
            'pc': hex(pc),
            'function': func_name,
            'addr_mode': 'INDIRECT',
            'offset': 0,
            'logical_addr': logical_addr
        }
    
    return None

def main():
    parser = argparse.ArgumentParser(description='Stage 8 v2: 分析读写操作（从反汇编）')
    parser.add_argument('elf_file', help='ELF文件')
    parser.add_argument('--output', default='build/reads_writes.json', help='输出JSON')
    
    args = parser.parse_args()
    
    print(f"  [Stage 8 v2] 从反汇编提取读写操作...")
    
    # 获取函数地址范围
    print(f"    - 提取函数符号表...")
    func_ranges = get_function_addr_ranges(args.elf_file)
    print(f"    - 找到 {len(func_ranges)} 个函数")
    
    # 反汇编
    print(f"    - 反汇编ELF文件...")
    disasm_lines = disassemble_elf(args.elf_file)
    
    # 分析读写
    print(f"    - 分析读写操作...")
    rw_data = analyze_reads_writes_from_disasm(disasm_lines, func_ranges)
    
    # 统计有PC的操作数
    reads_with_pc = [r for r in rw_data['reads'] if 'pc' in r and r['pc'] != 'NO_PC']
    writes_with_pc = [w for w in rw_data['writes'] if 'pc' in w and w['pc'] != 'NO_PC']
    
    # 输出JSON
    with open(args.output, 'w') as f:
        json.dump(rw_data, f, indent=2)
    
    print(f"  ✓ 分析读写操作完成:")
    print(f"    - 写操作: {len(rw_data['writes'])} ({len(writes_with_pc)} 个有PC)")
    print(f"    - 读操作: {len(rw_data['reads'])} ({len(reads_with_pc)} 个有PC)")
    print(f"  ✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

