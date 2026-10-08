#!/usr/bin/env python3
"""
Stage 2: 提取ELF .text段机器码
从编译好的ELF文件中提取.text段的纯机器码和元数据

输入: firmware.elf (编译好的固件)
输出: text_section.bin (纯机器码)
      section_info.json (段信息、符号表)

依赖: msp430-elf-objcopy, msp430-elf-objdump, msp430-elf-readelf
注意: 不需要Python库，直接使用MSP430工具链
"""

import argparse
import json
import subprocess
import sys
import re
import struct
from pathlib import Path


def extract_text_binary(elf_path, output_bin):
    """
    纯Python提取.text段二进制（不使用objcopy）
    直接解析ELF header和section header table
    
    Args:
        elf_path: ELF文件路径
        output_bin: 输出二进制文件路径
    """
    print(f"  方法: 纯Python ELF解析（不依赖objcopy）")
    
    try:
        from elf_parser import ELFParser
        
        # 创建解析器
        parser = ELFParser(elf_path)
        
        # 读取ELF数据
        with open(elf_path, 'rb') as f:
            elf_data = f.read()
        
        # 验证ELF Magic
        if elf_data[:4] != b'\x7fELF':
            print(f"  ✗ 不是有效的ELF文件")
            return False
        
        # 解析ELF header获取section header table位置
        e_shoff = struct.unpack('<I', elf_data[0x20:0x24])[0]      # Section header offset
        e_shentsize = struct.unpack('<H', elf_data[0x2E:0x30])[0]  # Section header entry size  
        e_shnum = struct.unpack('<H', elf_data[0x30:0x32])[0]      # Section header count
        e_shstrndx = struct.unpack('<H', elf_data[0x32:0x34])[0]   # String table index
        
        print(f"  → ELF Header: {e_shnum} sections, SHT offset=0x{e_shoff:04X}")
        
        # 读取section name string table
        shstrtab_offset = e_shoff + e_shstrndx * e_shentsize
        sh_name_off = struct.unpack('<I', elf_data[shstrtab_offset+0x10:shstrtab_offset+0x14])[0]
        sh_name_size = struct.unpack('<I', elf_data[shstrtab_offset+0x14:shstrtab_offset+0x18])[0]
        shstrtab = elf_data[sh_name_off:sh_name_off + sh_name_size]
        
        # 查找.text段
        text_section = None
        for i in range(e_shnum):
            sh_offset = e_shoff + i * e_shentsize
            
            # 解析section header (40字节)
            sh_name_idx = struct.unpack('<I', elf_data[sh_offset:sh_offset+4])[0]
            sh_type = struct.unpack('<I', elf_data[sh_offset+4:sh_offset+8])[0]
            sh_addr = struct.unpack('<I', elf_data[sh_offset+0x0C:sh_offset+0x10])[0]
            sh_file_offset = struct.unpack('<I', elf_data[sh_offset+0x10:sh_offset+0x14])[0]
            sh_size = struct.unpack('<I', elf_data[sh_offset+0x14:sh_offset+0x18])[0]
            
            # 读取section名称
            name_end = shstrtab.find(b'\x00', sh_name_idx)
            section_name = shstrtab[sh_name_idx:name_end].decode('utf-8')
            
            if section_name == '.text':
                text_section = {
                    'addr': sh_addr,
                    'offset': sh_file_offset,
                    'size': sh_size
                }
                print(f"  → 找到.text段: addr=0x{sh_addr:04X}, offset=0x{sh_file_offset:04X}, size={sh_size}")
                break
        
        if not text_section:
            print(f"  ✗ 未找到.text段")
            return False
        
        # 提取.text段数据
        text_data = elf_data[text_section['offset']:text_section['offset'] + text_section['size']]
        
        # 保存
        with open(output_bin, 'wb') as f:
            f.write(text_data)
        
        print(f"  ✓ 提取二进制成功: {output_bin} ({len(text_data)} 字节)")
        return True
        
    except Exception as e:
        print(f"  ✗ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def extract_section_info(elf_path):
    """
    纯Python提取.text段元数据（不依赖readelf/nm）
    直接解析ELF符号表
    
    Args:
        elf_path: ELF文件路径
    
    Returns:
        dict: 段信息，包含地址、大小、符号表等
    """
    from elf_parser import ELFParser
    
    parser = ELFParser(elf_path)
    parser.parse()
    
    text_info_raw = parser.get_section_info('.text')
    if not text_info_raw:
        raise ValueError("未找到.text段")
    
    text_info = {
        'name': '.text',
        'start_addr': text_info_raw['start_addr'],
        'offset': text_info_raw['offset'],
        'size': text_info_raw['size'],
        'alignment': text_info_raw.get('alignment', 2)
    }
    
    symbols = parser.parse_symbol_table()
    text_info['symbols'] = symbols
    
    text_info['stats'] = {
        'total_symbols': len(symbols),
        'function_symbols': sum(1 for s in symbols.values() if s['type'] == 'FUNC'),
        'object_symbols': sum(1 for s in symbols.values() if s['type'] == 'OBJECT'),
        'size_bytes': text_info['size']
    }
    
    return text_info


def print_section_summary(section_info):
    """打印段信息摘要"""
    print("\n" + "="*70)
    print("  .text 段信息摘要")
    print("="*70)
    print(f"  起始地址:   0x{section_info['start_addr']:04X}")
    print(f"  大小:       {section_info['size']} 字节")
    print(f"  文件偏移:   0x{section_info['offset']:04X}")
    print(f"  对齐:       {section_info['alignment']} 字节")
    
    stats = section_info['stats']
    print(f"\n  符号统计:")
    print(f"    总符号数:   {stats['total_symbols']}")
    print(f"    函数符号:   {stats['function_symbols']}")
    print(f"    对象符号:   {stats['object_symbols']}")
    
    # 显示前10个函数符号
    func_symbols = {name: info for name, info in section_info['symbols'].items()
                   if info['type'] == 'FUNC'}
    
    if func_symbols:
        print(f"\n  主要函数符号 (前10个):")
        for name, info in sorted(func_symbols.items(), 
                                key=lambda x: x[1]['address'])[:10]:
            print(f"    0x{info['address']:04X}  {info['size']:4d}B  {name}")
        
        if len(func_symbols) > 10:
            print(f"    ... 还有 {len(func_symbols) - 10} 个函数")
    
    print("="*70)


def verify_extraction(bin_path, expected_size):
    """验证提取的二进制文件"""
    if not bin_path.exists():
        print(f"  ✗ 错误: 文件不存在 {bin_path}")
        return False
    
    actual_size = bin_path.stat().st_size
    if actual_size != expected_size:
        print(f"  ⚠ 警告: 文件大小不匹配")
        print(f"    预期: {expected_size} 字节")
        print(f"    实际: {actual_size} 字节")
        return False
    
    print(f"  ✓ 验证通过: {actual_size} 字节")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='从ELF文件提取.text段机器码',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python stage2_extract_text.py firmware.elf
  python stage2_extract_text.py firmware.elf --output-dir build/machine_code
        """
    )
    
    parser.add_argument('elf_file', 
                       help='输入ELF文件路径')
    parser.add_argument('--output-dir', 
                       default='build/machine_code',
                       help='输出目录 (默认: build/machine_code)')
    parser.add_argument('--binary-name',
                       default='text_section.bin',
                       help='二进制文件名 (默认: text_section.bin)')
    parser.add_argument('--json-name',
                       default='section_info.json',
                       help='JSON文件名 (默认: section_info.json)')
    
    args = parser.parse_args()
    
    # 检查输入文件
    elf_path = Path(args.elf_file)
    if not elf_path.exists():
        print(f"错误: 文件不存在: {elf_path}")
        sys.exit(1)
    
    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_bin = output_dir / args.binary_name
    output_json = output_dir / args.json_name
    
    print(f"  输入:  {elf_path}")
    print(f"  输出目录: {output_dir}")
    print()
    
    # 步骤1: 提取二进制
    print("[1/3] 提取二进制机器码...")
    if not extract_text_binary(elf_path, output_bin):
        sys.exit(1)
    
    # 步骤2: 提取元数据
    print("\n[2/3] 提取段元数据和符号表...")
    try:
        section_info = extract_section_info(elf_path)
        print(f"  ✓ 提取元数据成功")
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        sys.exit(1)
    
    # 步骤3: 验证和保存
    print("\n[3/3] 验证并保存结果...")
    if not verify_extraction(output_bin, section_info['size']):
        sys.exit(1)
    
    # 保存JSON
    with open(output_json, 'w') as f:
        json.dump(section_info, f, indent=2)
    print(f"  ✓ 保存元数据: {output_json}")
    
    # 打印摘要
    print_section_summary(section_info)
    
    print(f"  二进制: {output_bin}")
    print(f"  元数据: {output_json}")
    print()


if __name__ == '__main__':
    main()

