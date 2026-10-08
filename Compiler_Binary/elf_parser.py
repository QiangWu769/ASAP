#!/usr/bin/env python3
"""
纯Python ELF解析器
直接从ELF header和section header table提取.text段
完全不依赖objcopy等外部工具

ELF格式参考: http://www.skyfree.org/linux/references/ELF_Format.pdf
MSP430 ELF格式: 32-bit Little Endian
"""

import struct
from pathlib import Path


class ELFParser:
    """ELF文件解析器"""
    
    # ELF Magic Number
    ELF_MAGIC = b'\x7fELF'
    
    # ELF类型
    ELFCLASS32 = 1
    ELFCLASS64 = 2
    
    # 字节序
    ELFDATA2LSB = 1  # Little Endian
    ELFDATA2MSB = 2  # Big Endian
    
    # Section类型
    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHT_NOBITS = 8
    
    # Symbol类型
    STT_NOTYPE = 0
    STT_OBJECT = 1
    STT_FUNC = 2
    STT_SECTION = 3
    STT_FILE = 4
    
    # Symbol绑定
    STB_LOCAL = 0
    STB_GLOBAL = 1
    STB_WEAK = 2
    
    def __init__(self, elf_path):
        """
        初始化ELF解析器
        
        Args:
            elf_path: ELF文件路径
        """
        self.elf_path = Path(elf_path)
        self.elf_data = None
        self.elf_header = {}
        self.section_headers = []
        self.sections = {}
        
    def parse(self):
        """解析ELF文件"""
        print(f"📖 解析ELF文件: {self.elf_path}")
        
        # 读取完整文件
        with open(self.elf_path, 'rb') as f:
            self.elf_data = f.read()
        
        # 1. 解析ELF Header
        self._parse_elf_header()
        
        # 2. 解析Section Header Table
        self._parse_section_headers()
        
        # 3. 解析Section内容
        self._parse_sections()
        
        print(f"[OK] 解析完成: {len(self.section_headers)} 个section")
        
    def _parse_elf_header(self):
        """解析ELF Header"""
        print("\n[1/3] 解析ELF Header...")
        
        # 验证Magic Number
        if self.elf_data[:4] != self.ELF_MAGIC:
            raise ValueError("不是有效的ELF文件")
        
        # ELF识别信息 (e_ident)
        ei_class = self.elf_data[4]  # 1=32bit, 2=64bit
        ei_data = self.elf_data[5]   # 1=little endian, 2=big endian
        ei_version = self.elf_data[6]
        
        if ei_class != self.ELFCLASS32:
            raise ValueError("只支持32位ELF文件")
        
        if ei_data != self.ELFDATA2LSB:
            raise ValueError("只支持Little Endian")
        
        self.elf_header['class'] = ei_class
        self.elf_header['endian'] = ei_data
        
        # 解析ELF Header (32-bit格式)
        # Offset 0x10: e_type (2 bytes)
        e_type = struct.unpack('<H', self.elf_data[0x10:0x12])[0]
        # Offset 0x12: e_machine (2 bytes)
        e_machine = struct.unpack('<H', self.elf_data[0x12:0x14])[0]
        # Offset 0x14: e_version (4 bytes)
        e_version = struct.unpack('<I', self.elf_data[0x14:0x18])[0]
        # Offset 0x18: e_entry (4 bytes)
        e_entry = struct.unpack('<I', self.elf_data[0x18:0x1C])[0]
        # Offset 0x1C: e_phoff (4 bytes) - Program header offset
        e_phoff = struct.unpack('<I', self.elf_data[0x1C:0x20])[0]
        # Offset 0x20: e_shoff (4 bytes) - Section header offset
        e_shoff = struct.unpack('<I', self.elf_data[0x20:0x24])[0]
        # Offset 0x24: e_flags (4 bytes)
        e_flags = struct.unpack('<I', self.elf_data[0x24:0x28])[0]
        # Offset 0x28: e_ehsize (2 bytes) - ELF header size
        e_ehsize = struct.unpack('<H', self.elf_data[0x28:0x2A])[0]
        # Offset 0x2A: e_phentsize (2 bytes)
        e_phentsize = struct.unpack('<H', self.elf_data[0x2A:0x2C])[0]
        # Offset 0x2C: e_phnum (2 bytes)
        e_phnum = struct.unpack('<H', self.elf_data[0x2C:0x2E])[0]
        # Offset 0x2E: e_shentsize (2 bytes) - Section header entry size
        e_shentsize = struct.unpack('<H', self.elf_data[0x2E:0x30])[0]
        # Offset 0x30: e_shnum (2 bytes) - Section header count
        e_shnum = struct.unpack('<H', self.elf_data[0x30:0x32])[0]
        # Offset 0x32: e_shstrndx (2 bytes) - Section name string table index
        e_shstrndx = struct.unpack('<H', self.elf_data[0x32:0x34])[0]
        
        self.elf_header.update({
            'type': e_type,
            'machine': e_machine,
            'version': e_version,
            'entry': e_entry,
            'phoff': e_phoff,
            'shoff': e_shoff,
            'flags': e_flags,
            'ehsize': e_ehsize,
            'phentsize': e_phentsize,
            'phnum': e_phnum,
            'shentsize': e_shentsize,
            'shnum': e_shnum,
            'shstrndx': e_shstrndx
        })
        
        print(f"  ✓ ELF类型: 32-bit Little Endian")
        print(f"  ✓ 入口地址: 0x{e_entry:04X}")
        print(f"  ✓ Section数量: {e_shnum}")
        print(f"  ✓ Section Header偏移: 0x{e_shoff:04X}")
        
    def _parse_section_headers(self):
        """解析Section Header Table"""
        print("\n[2/3] 解析Section Header Table...")
        
        shoff = self.elf_header['shoff']
        shentsize = self.elf_header['shentsize']
        shnum = self.elf_header['shnum']
        shstrndx = self.elf_header['shstrndx']
        
        # 先解析section name string table
        shstrtab_offset = shoff + shstrndx * shentsize
        shstrtab_header = self._parse_section_header_at(shstrtab_offset)
        shstrtab_data = self.elf_data[shstrtab_header['offset']:
                                       shstrtab_header['offset'] + shstrtab_header['size']]
        
        # 解析所有section headers
        for i in range(shnum):
            sh_offset = shoff + i * shentsize
            sh = self._parse_section_header_at(sh_offset)
            
            # 读取section名称
            name_offset = sh['name_offset']
            name_end = shstrtab_data.find(b'\x00', name_offset)
            sh['name'] = shstrtab_data[name_offset:name_end].decode('utf-8')
            
            self.section_headers.append(sh)
        
        print(f"  ✓ 解析了 {len(self.section_headers)} 个section header")
        
        # 显示主要sections
        for sh in self.section_headers:
            if sh['name'] in ['.text', '.data', '.bss', '.rodata', '.symtab', '.strtab']:
                print(f"    - {sh['name']:15s} offset=0x{sh['offset']:04X} size={sh['size']:5d} addr=0x{sh['addr']:04X}")
    
    def _parse_section_header_at(self, offset):
        """
        解析指定偏移处的Section Header (32-bit)
        
        Section Header结构 (40字节):
          0x00: sh_name (4 bytes) - name offset in string table
          0x04: sh_type (4 bytes)
          0x08: sh_flags (4 bytes)
          0x0C: sh_addr (4 bytes) - virtual address
          0x10: sh_offset (4 bytes) - file offset
          0x14: sh_size (4 bytes)
          0x18: sh_link (4 bytes)
          0x1C: sh_info (4 bytes)
          0x20: sh_addralign (4 bytes)
          0x24: sh_entsize (4 bytes)
        """
        data = self.elf_data[offset:offset+40]
        
        return {
            'name_offset': struct.unpack('<I', data[0x00:0x04])[0],
            'type': struct.unpack('<I', data[0x04:0x08])[0],
            'flags': struct.unpack('<I', data[0x08:0x0C])[0],
            'addr': struct.unpack('<I', data[0x0C:0x10])[0],
            'offset': struct.unpack('<I', data[0x10:0x14])[0],
            'size': struct.unpack('<I', data[0x14:0x18])[0],
            'link': struct.unpack('<I', data[0x18:0x1C])[0],
            'info': struct.unpack('<I', data[0x1C:0x20])[0],
            'addralign': struct.unpack('<I', data[0x20:0x24])[0],
            'entsize': struct.unpack('<I', data[0x24:0x28])[0],
        }
    
    def _parse_sections(self):
        """解析Section内容"""
        print("\n[3/3] 提取Section数据...")
        
        for sh in self.section_headers:
            if sh['type'] == self.SHT_NOBITS:
                # .bss等，没有实际数据
                self.sections[sh['name']] = None
            else:
                # 提取数据
                data = self.elf_data[sh['offset']:sh['offset'] + sh['size']]
                self.sections[sh['name']] = {
                    'data': data,
                    'addr': sh['addr'],
                    'size': sh['size'],
                    'offset': sh['offset'],
                    'type': sh['type']
                }
        
        print(f"  ✓ 提取了 {len(self.sections)} 个section的数据")
    
    def extract_section(self, section_name):
        """
        提取指定section的二进制数据
        
        Args:
            section_name: section名称 (如 '.text')
        
        Returns:
            bytes: section的二进制数据
        """
        if section_name not in self.sections:
            raise ValueError(f"Section '{section_name}' 不存在")
        
        section = self.sections[section_name]
        if section is None:
            raise ValueError(f"Section '{section_name}' 没有数据 (SHT_NOBITS)")
        
        return section['data']
    
    def get_section_info(self, section_name):
        """
        获取section信息
        
        Returns:
            dict: {
                'start_addr': 起始地址,
                'size': 大小,
                'offset': 文件偏移,
                'alignment': 对齐
            }
        """
        for sh in self.section_headers:
            if sh['name'] == section_name:
                return {
                    'start_addr': sh['addr'],
                    'size': sh['size'],
                    'offset': sh['offset'],
                    'alignment': sh['addralign']
                }
        return None
    
    def parse_symbol_table(self):
        """
        解析符号表
        
        Returns:
            dict: {symbol_name: {address, size, type, bind}}
        """
        # 找到.symtab和.strtab
        symtab_section = None
        strtab_section = None
        
        for sh in self.section_headers:
            if sh['name'] == '.symtab':
                symtab_section = sh
            elif sh['name'] == '.strtab':
                strtab_section = sh
        
        if not symtab_section or not strtab_section:
            return {}
        
        # 读取字符串表
        strtab_data = self.elf_data[strtab_section['offset']:
                                     strtab_section['offset'] + strtab_section['size']]
        
        # 解析符号表
        symbols = {}
        symtab_data = self.elf_data[symtab_section['offset']:
                                     symtab_section['offset'] + symtab_section['size']]
        
        # 每个符号表项16字节 (32-bit ELF)
        num_symbols = len(symtab_data) // 16
        
        for i in range(num_symbols):
            offset = i * 16
            
            # Symbol结构 (16字节):
            #   0x00: st_name (4 bytes)
            #   0x04: st_value (4 bytes) - address
            #   0x08: st_size (4 bytes)
            #   0x0C: st_info (1 byte) - type and binding
            #   0x0D: st_other (1 byte)
            #   0x0E: st_shndx (2 bytes)
            st_name_offset = struct.unpack('<I', symtab_data[offset:offset+4])[0]
            st_value = struct.unpack('<I', symtab_data[offset+4:offset+8])[0]
            st_size = struct.unpack('<I', symtab_data[offset+8:offset+12])[0]
            st_info = symtab_data[offset+12]
            st_other = symtab_data[offset+13]
            st_shndx = struct.unpack('<H', symtab_data[offset+14:offset+16])[0]
            
            # 提取类型和绑定
            st_type = st_info & 0x0F
            st_bind = (st_info >> 4) & 0x0F
            
            # 读取符号名
            if st_name_offset < len(strtab_data):
                name_end = strtab_data.find(b'\x00', st_name_offset)
                if name_end == -1:
                    name_end = len(strtab_data)
                sym_name = strtab_data[st_name_offset:name_end].decode('utf-8', errors='ignore')
            else:
                sym_name = ''
            
            if sym_name and st_type == self.STT_FUNC:
                type_str = {0: 'NOTYPE', 1: 'OBJECT', 2: 'FUNC', 3: 'SECTION', 4: 'FILE'}.get(st_type, 'UNKNOWN')
                bind_str = {0: 'LOCAL', 1: 'GLOBAL', 2: 'WEAK'}.get(st_bind, 'UNKNOWN')
                
                symbols[sym_name] = {
                    'address': st_value,
                    'size': st_size,
                    'type': type_str,
                    'bind': bind_str,
                    'offset': st_value - self.get_section_info('.text')['start_addr'] if st_value > 0 else 0
                }
        
        return symbols


def extract_text_section_pure_python(elf_path, output_bin, output_json):
    """
    纯Python实现：从ELF文件提取.text段
    完全不使用objcopy等外部工具
    
    Args:
        elf_path: ELF文件路径
        output_bin: 输出二进制文件路径
        output_json: 输出元数据JSON文件路径
    """
    print("="*70)
    print("  纯Python ELF解析 - 提取.text段")
    print("="*70)
    print(f"  输入: {elf_path}")
    print()
    
    # 创建解析器
    parser = ELFParser(elf_path)
    
    # 解析ELF
    parser.parse()
    
    # 提取.text段
    print("\n" + "="*70)
    print("  提取.text段")
    print("="*70)
    
    text_data = parser.extract_section('.text')
    text_info = parser.get_section_info('.text')
    
    print(f"  ✓ 提取成功: {len(text_data)} 字节")
    print(f"  ✓ 起始地址: 0x{text_info['start_addr']:04X}")
    
    # 保存二进制
    with open(output_bin, 'wb') as f:
        f.write(text_data)
    print(f"  ✓ 保存二进制: {output_bin}")
    
    # 解析符号表
    symbols = parser.parse_symbol_table()
    
    # 保存元数据
    import json
    metadata = {
        'name': '.text',
        'start_addr': text_info['start_addr'],
        'offset': text_info['offset'],
        'size': text_info['size'],
        'alignment': text_info['alignment'],
        'symbols': symbols,
        'stats': {
            'total_symbols': len(symbols),
            'function_symbols': sum(1 for s in symbols.values() if s['type'] == 'FUNC'),
            'object_symbols': sum(1 for s in symbols.values() if s['type'] == 'OBJECT'),
            'size_bytes': len(text_data)
        }
    }
    
    with open(output_json, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  ✓ 保存元数据: {output_json}")
    
    # 打印摘要
    print("\n" + "="*70)
    print("  .text段信息摘要")
    print("="*70)
    print(f"  起始地址:   0x{text_info['start_addr']:04X}")
    print(f"  大小:       {len(text_data)} 字节")
    print(f"  文件偏移:   0x{text_info['offset']:04X}")
    print(f"  对齐:       {text_info['alignment']} 字节")
    print()
    print(f"  符号统计:")
    print(f"    总符号数:   {len(symbols)}")
    print(f"    函数符号:   {metadata['stats']['function_symbols']}")
    print(f"    对象符号:   {metadata['stats']['object_symbols']}")
    print()
    
    # 显示主要函数
    func_symbols = [(name, info) for name, info in symbols.items() if info['type'] == 'FUNC']
    func_symbols.sort(key=lambda x: x[1]['address'])
    
    if func_symbols:
        print(f"  主要函数符号 (前10个):")
        for name, info in func_symbols[:10]:
            size_str = f"{info['size']:3d}B" if info['size'] > 0 else "  0B"
            print(f"    0x{info['address']:04X}  {size_str}  {name}")
        if len(func_symbols) > 10:
            print(f"    ... 还有 {len(func_symbols) - 10} 个函数")
    
    print("="*70)
    print()
    print("[OK] .text段提取完成!")
    print(f"  二进制: {output_bin}")
    print(f"  元数据: {output_json}")
    print()
    
    return metadata


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 4:
        print("用法: python elf_parser.py <input.elf> <output.bin> <output.json>")
        sys.exit(1)
    
    elf_path = sys.argv[1]
    output_bin = sys.argv[2]
    output_json = sys.argv[3]
    
    extract_text_section_pure_python(elf_path, output_bin, output_json)






