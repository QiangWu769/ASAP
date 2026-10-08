#!/usr/bin/env python3
"""
分析寄存器间接寻址，尝试将其转换为直接地址
目标：识别 @Rn 访问，追踪Rn的值，如果可能转换为绝对地址
"""
import argparse
import json
import re
import subprocess

def disassemble_elf(elf_file):
    """反汇编.elf文件"""
    result = subprocess.run(
        ['msp430-elf-objdump', '-d', elf_file],
        capture_output=True,
        text=True
    )
    return result.stdout.split('\n')

def parse_instruction(line):
    """解析一条反汇编指令"""
    # "    88f8:	82 41 00 65 	mov	r1,	&0x6500	;"
    match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f\s]+)\s+(.+)', line, re.IGNORECASE)
    if not match:
        return None
    
    pc = int(match.group(1), 16)
    instruction = match.group(3).split(';')[0].strip()
    instruction = re.sub(r'\s+', ' ', instruction)
    
    return {
        'pc': pc,
        'hex_pc': hex(pc),
        'instruction': instruction
    }

def find_indirect_addressing(disasm_lines):
    """找到所有使用寄存器间接寻址的指令"""
    
    indirect_accesses = []
    
    for line in disasm_lines:
        instr = parse_instruction(line)
        if not instr:
            continue
        
        instruction = instr['instruction']
        
        # 检测 @Rn 模式（寄存器间接）
        # 例如: mov r12, @r9
        if '@r' in instruction.lower():
            # 提取使用的寄存器
            reg_match = re.findall(r'@r(\d+)', instruction, re.IGNORECASE)
            if reg_match:
                for reg_num in reg_match:
                    indirect_accesses.append({
                        'pc': instr['hex_pc'],
                        'instruction': instruction,
                        'indirect_reg': f'R{reg_num}',
                        'type': 'indirect'
                    })
    
    return indirect_accesses

def trace_register_value(disasm_lines, target_pc, target_reg):
    """回溯追踪寄存器的值是如何计算的
    
    从target_pc向前扫描，找到target_reg的定义
    """
    
    instructions = []
    for line in disasm_lines:
        instr = parse_instruction(line)
        if instr:
            instructions.append(instr)
    
    # 找到目标指令的索引
    target_idx = None
    for i, instr in enumerate(instructions):
        if instr['pc'] == int(target_pc, 16):
            target_idx = i
            break
    
    if target_idx is None:
        return None
    
    # 向前扫描，找到对target_reg的写入
    trace_chain = []
    current_reg = target_reg.lower()
    
    for i in range(target_idx - 1, max(0, target_idx - 50), -1):
        instr = instructions[i]['instruction'].lower()
        
        # 检查是否对目标寄存器赋值
        # mov xxx, rN
        # add xxx, rN
        # lea xxx, rN (load effective address)
        
        # 匹配: instruction src, dst
        match = re.match(r'(\w+)\s+([^,]+),\s*(.+)', instr)
        if not match:
            continue
        
        opcode = match.group(1)
        src = match.group(2).strip()
        dst = match.group(3).strip()
        
        # 如果目标寄存器被写入
        if dst == current_reg or dst.startswith(current_reg + ' '):
            trace_chain.append({
                'pc': instructions[i]['hex_pc'],
                'instruction': instructions[i]['instruction'],
                'opcode': opcode,
                'src': src,
                'dst': dst
            })
            
            # 如果是MOV，继续追踪源
            if opcode == 'mov' and src.startswith('r'):
                current_reg = src
            # 如果是ADD，检查是否是地址计算
            elif opcode == 'add':
                # R9 = base + offset 这种模式
                pass
            else:
                break
            
            # 限制追踪深度
            if len(trace_chain) >= 10:
                break
    
    return trace_chain

def analyze_address_calculation(trace_chain):
    """分析追踪链，判断是否可以转换为直接地址"""
    
    if not trace_chain:
        return None
    
    # 简单模式：R9 = &base; R9 += offset
    # 或: R9 = SP+offset
    
    result = {
        'can_convert': False,
        'base': None,
        'offset': 0,
        'pattern': 'unknown'
    }
    
    # 检查最近的一次赋值
    last = trace_chain[0]
    
    # 模式1: mov &0x1234, rN (加载绝对地址)
    if last['opcode'] == 'mov' and '&0x' in last['src']:
        addr_match = re.search(r'&(0x[0-9a-f]+)', last['src'], re.IGNORECASE)
        if addr_match:
            result['can_convert'] = True
            result['base'] = addr_match.group(1)
            result['pattern'] = 'absolute_address'
    
    # 模式2: mov rN, rM (寄存器复制，需要继续追踪)
    elif last['opcode'] == 'mov' and last['src'].startswith('r'):
        result['pattern'] = 'register_copy'
    
    # 模式3: add #offset, rN (地址偏移)
    elif last['opcode'] == 'add':
        offset_match = re.search(r'#(-?\d+)', last['src'])
        if offset_match:
            result['offset'] = int(offset_match.group(1))
            result['pattern'] = 'offset_added'
    
    return result

def main():
    parser = argparse.ArgumentParser(description='分析寄存器间接寻址')
    parser.add_argument('elf_file', help='ELF文件')
    parser.add_argument('--output', default='build/indirect_analysis.json', help='输出JSON')
    
    args = parser.parse_args()
    
    print("🔍 分析寄存器间接寻址...")
    
    # 反汇编
    print("  - 反汇编ELF文件...")
    disasm_lines = disassemble_elf(args.elf_file)
    
    # 找到所有间接寻址
    print("  - 查找间接寻址指令...")
    indirect_accesses = find_indirect_addressing(disasm_lines)
    print(f"    找到 {len(indirect_accesses)} 个寄存器间接寻址")
    
    # 追踪每个间接访问的寄存器值
    print("  - 追踪寄存器值...")
    analysis_results = []
    
    for access in indirect_accesses[:20]:  # 先分析前20个
        pc = access['pc']
        reg = access['indirect_reg']
        
        trace = trace_register_value(disasm_lines, pc, reg)
        addr_info = analyze_address_calculation(trace)
        
        analysis_results.append({
            'pc': pc,
            'instruction': access['instruction'],
            'indirect_reg': reg,
            'trace_chain': trace if trace else [],
            'address_info': addr_info
        })
    
    # 输出结果
    output_data = {
        'total_indirect_accesses': len(indirect_accesses),
        'analyzed': analysis_results
    }
    
    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    # 显示可转换的情况
    convertible = [r for r in analysis_results if r['address_info'] and r['address_info']['can_convert']]
    
    print(f"\n✓ 分析完成:")
    print(f"  - 总间接寻址: {len(indirect_accesses)}")
    print(f"  - 已分析: {len(analysis_results)}")
    print(f"  - 可转换为直接地址: {len(convertible)}")
    
    if convertible:
        print(f"\n  可转换示例:")
        for r in convertible[:5]:
            print(f"    {r['pc']}: {r['instruction']}")
            print(f"      → 基地址: {r['address_info']['base']}")
    
    print(f"\n✓ 输出: {args.output}")

if __name__ == '__main__':
    main()

























