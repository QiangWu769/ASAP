#!/usr/bin/env python3
"""
Stage 3: 反汇编机器码
使用objdump反汇编.text段，解析为结构化数据

输入: text_section.bin, section_info.json
输出: instructions.json (所有指令的详细信息)

依赖: msp430-elf-objdump
注意: 不依赖Python库，使用MSP430工具链
"""

import argparse
import json
import subprocess
import sys
import re
from pathlib import Path


def disassemble_binary(bin_path, section_info):
    """
    使用objdump反汇编二进制文件
    
    Args:
        bin_path: 二进制文件路径
        section_info: 段信息(包含起始地址)
    
    Returns:
        str: objdump的反汇编输出
    """
    base_addr = section_info['start_addr']
    
    # 使用objdump反汇编
    cmd = [
        'msp430-elf-objdump',
        '-D',  # 反汇编所有内容
        '-b', 'binary',  # 输入是纯二进制
        '-m', 'msp430',  # 目标架构
        f'--adjust-vma=0x{base_addr:x}',  # 调整显示地址
        str(bin_path)
    ]
    
    print(f"  执行: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  ✓ 反汇编成功")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"  ✗ objdump失败:")
        print(e.stderr)
        sys.exit(1)


def parse_disassembly(disasm_text, base_addr):
    """
    解析objdump的反汇编输出为结构化数据
    
    Args:
        disasm_text: objdump输出
        base_addr: .text段起始地址
    
    Returns:
        list: 指令列表
    """
    instructions = []
    
    # objdump输出示例:
    #    4402:       31 40 00 24     mov     #9216,  r1      ;#0x2400
    #    4414:       b1 40 0a 00     mov     #10,    4(r1)   ;#0x000a
    #    4418:       04 00           (continuation of previous instruction)
    
    # 匹配完整指令行（带助记符）
    pattern = re.compile(
        r'^\s*([0-9a-f]+):\s+'        # 地址
        r'([0-9a-f ]+?)\s+'            # 机器码字节
        r'([a-z]+(?:\.[bw])?)\s+'      # 助记符 (mov, add.w, etc.)
        r'(.*)$'                       # 操作数和注释
    )
    
    # 匹配续行（只有字节，无助记符）
    continuation_pattern = re.compile(
        r'^\s*([0-9a-f]+):\s+'        # 地址
        r'([0-9a-f ]+?)\s*$'           # 只有字节
    )
    
    lines = disasm_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        match = pattern.match(line)
        
        if match:
            addr_str = match.group(1)
            bytes_str = match.group(2)
            mnemonic = match.group(3)
            operands_str = match.group(4)
            
            # 解析地址
            address = int(addr_str, 16)
            offset = address - base_addr
            
            # 收集所有字节（包括续行）
            all_bytes = bytes_str
            
            # 检查下一行是否是续行
            j = i + 1
            while j < len(lines):
                next_match = continuation_pattern.match(lines[j])
                if next_match:
                    # 是续行，添加字节
                    all_bytes += ' ' + next_match.group(2)
                    j += 1
                else:
                    # 不是续行，停止
                    break
            
            # 解析所有字节
            bytes_hex = all_bytes.replace(' ', '')
            machine_bytes = [int(bytes_hex[k:k+2], 16) 
                            for k in range(0, len(bytes_hex), 2)]
            
            # 解析操作数（移除注释）
            if ';' in operands_str:
                operands_str = operands_str.split(';')[0].strip()
            
            # 分割操作数
            operands = []
            if operands_str:
                # 用逗号分割
                for op_str in operands_str.split(','):
                    op_str = op_str.strip()
                    if op_str:  # 跳过空字符串
                        operands.append(parse_operand(op_str))
            
            # 构建指令信息
            instruction = {
                'offset': offset,
                'address': address,
                'mnemonic': mnemonic,
                'operands': operands,
                'operands_str': operands_str,
                'bytes': machine_bytes,
                'size': len(machine_bytes)
            }
            
            instructions.append(instruction)
            
            # 跳过已处理的续行
            i = j
        else:
            i += 1
    
    return instructions


def parse_operand(op_str):
    """
    解析单个操作数
    
    支持的格式:
      - r12, r13, r1等 (寄存器)
      - #10, #0x1234 (立即数)
      - 6(r1), 100(r12) (索引寻址)
      - @r12, @r13 (寄存器间接)
      - &0x4800 (绝对地址)
    
    Returns:
        dict: 操作数信息
    """
    op_str = op_str.strip()
    
    # 立即数: #value
    if op_str.startswith('#'):
        value_str = op_str[1:]
        value = int(value_str, 0)  # 自动识别10进制/16进制
        return {
            'type': 'immediate',
            'value': value,
            'str': op_str
        }
    
    # 绝对地址: &0xABCD
    if op_str.startswith('&'):
        addr_str = op_str[1:]
        addr = int(addr_str, 0)
        return {
            'type': 'absolute',
            'address': addr,
            'str': op_str
        }
    
    # 索引寻址: offset(reg)
    indexed_match = re.match(r'(-?\d+)\((r\d+)\)', op_str, re.IGNORECASE)
    if indexed_match:
        offset = int(indexed_match.group(1))
        reg = indexed_match.group(2).lower()
        return {
            'type': 'indexed',
            'base_reg': reg,
            'offset': offset,
            'str': op_str
        }
    
    # 寄存器间接: @reg
    if op_str.startswith('@'):
        reg = op_str[1:].lower()
        return {
            'type': 'indirect',
            'reg': reg,
            'str': op_str
        }
    
    # 寄存器直接: r12
    if op_str.startswith('r') or op_str.upper() in ['SP', 'PC', 'SR']:
        return {
            'type': 'register',
            'reg': op_str.lower(),
            'str': op_str
        }
    
    # 其他（标签等）
    return {
        'type': 'other',
        'value': op_str,
        'str': op_str
    }


def print_disassembly_summary(instructions):
    """打印反汇编摘要"""
    print("\n" + "="*70)
    print("  反汇编结果摘要")
    print("="*70)
    print(f"  总指令数: {len(instructions)}")
    
    # 统计指令类型
    mnemonics = {}
    for instr in instructions:
        m = instr['mnemonic']
        mnemonics[m] = mnemonics.get(m, 0) + 1
    
    print(f"\n  指令分布 (前10种):")
    for m, count in sorted(mnemonics.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"    {m:10s}: {count:4d}")
    
    # 显示前10条指令
    print(f"\n  前10条指令:")
    for instr in instructions[:10]:
        bytes_str = ' '.join(f'{b:02x}' for b in instr['bytes'])
        print(f"    0x{instr['address']:04X}  {bytes_str:20s}  {instr['mnemonic']:8s} {instr['operands_str']}")
    
    if len(instructions) > 10:
        print(f"    ... 还有 {len(instructions) - 10} 条指令")
    
    print("="*70)


def main():
    parser = argparse.ArgumentParser(
        description='反汇编.text段机器码',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python stage3_disassemble.py build/machine_code/text_section.bin
  python stage3_disassemble.py text.bin --section-info section_info.json
        """
    )
    
    parser.add_argument('binary_file',
                       help='输入二进制文件 (text_section.bin)')
    parser.add_argument('--section-info',
                       default='build/machine_code/section_info.json',
                       help='段信息JSON (默认: build/machine_code/section_info.json)')
    parser.add_argument('--output',
                       default='build/machine_code/instructions.json',
                       help='输出JSON (默认: build/machine_code/instructions.json)')
    
    args = parser.parse_args()
    
    # 检查输入文件
    bin_path = Path(args.binary_file)
    if not bin_path.exists():
        print(f"错误: 文件不存在: {bin_path}")
        sys.exit(1)
    
    section_info_path = Path(args.section_info)
    if not section_info_path.exists():
        print(f"错误: 文件不存在: {section_info_path}")
        sys.exit(1)
    
    # 读取段信息
    with open(section_info_path, 'r') as f:
        section_info = json.load(f)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  输入: {bin_path}")
    print(f"  基址: 0x{section_info['start_addr']:04X}")
    print(f"  大小: {section_info['size']} 字节")
    print()
    
    from msp430_disasm_rigorous import disassemble_with_rigorous_algorithm
    
    result_data = disassemble_with_rigorous_algorithm(
        str(bin_path),
        section_info['start_addr'],
        str(output_path),
        verbose=True  # 显示详细解码过程（前10条）
    )
    
    print(f"\n[2/2] 统计结果...")
    print(f"  ✓ 解码指令: {result_data['instruction_count']} 条")
    
    print(f"\n✅ Stage 3 完成!")
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()

