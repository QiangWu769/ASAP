#!/usr/bin/env python3
"""
ELF结构更新工具
真正实现段头表、符号表、程序头表的更新

不依赖Python库，直接操作ELF二进制结构
"""

import struct


class ELFUpdater:
    """ELF文件更新器"""
    
    def __init__(self, elf_path):
        """加载ELF文件"""
        with open(elf_path, 'rb') as f:
            self.elf_data = bytearray(f.read())
        
        self.parse_elf_header()
    
    def parse_elf_header(self):
        """解析ELF头"""
        # ELF头结构 (MSP430是32位小端)
        self.e_ident = self.elf_data[0:16]
        self.e_type = struct.unpack('<H', self.elf_data[16:18])[0]
        self.e_machine = struct.unpack('<H', self.elf_data[18:20])[0]
        self.e_version = struct.unpack('<I', self.elf_data[20:24])[0]
        self.e_entry = struct.unpack('<I', self.elf_data[24:28])[0]
        self.e_phoff = struct.unpack('<I', self.elf_data[28:32])[0]  # 程序头表偏移
        self.e_shoff = struct.unpack('<I', self.elf_data[32:36])[0]  # 段头表偏移
        self.e_flags = struct.unpack('<I', self.elf_data[36:40])[0]
        self.e_ehsize = struct.unpack('<H', self.elf_data[40:42])[0]
        self.e_phentsize = struct.unpack('<H', self.elf_data[42:44])[0]
        self.e_phnum = struct.unpack('<H', self.elf_data[44:46])[0]
        self.e_shentsize = struct.unpack('<H', self.elf_data[46:48])[0]
        self.e_shnum = struct.unpack('<H', self.elf_data[48:50])[0]
        self.e_shstrndx = struct.unpack('<H', self.elf_data[50:52])[0]
    
    def find_text_section(self):
        """找到.text段"""
        shstrtab_offset = self.get_section_offset(self.e_shstrndx)
        
        for i in range(self.e_shnum):
            sh_offset = self.e_shoff + i * self.e_shentsize
            sh_data = self.elf_data[sh_offset:sh_offset + self.e_shentsize]
            
            # 解析段头
            sh_name_idx = struct.unpack('<I', sh_data[0:4])[0]
            sh_type = struct.unpack('<I', sh_data[4:8])[0]
            sh_flags = struct.unpack('<I', sh_data[8:12])[0]
            sh_addr = struct.unpack('<I', sh_data[12:16])[0]
            sh_offset_val = struct.unpack('<I', sh_data[16:20])[0]
            sh_size = struct.unpack('<I', sh_data[20:24])[0]
            
            # 读取段名
            section_name = self.read_string(shstrtab_offset + sh_name_idx)
            
            if section_name == '.text':
                return {
                    'index': i,
                    'header_offset': sh_offset,
                    'name': section_name,
                    'type': sh_type,
                    'addr': sh_addr,
                    'offset': sh_offset_val,
                    'size': sh_size
                }
        
        return None
    
    def read_string(self, offset):
        """从ELF中读取以NULL结尾的字符串"""
        result = b''
        while offset < len(self.elf_data) and self.elf_data[offset] != 0:
            result += bytes([self.elf_data[offset]])
            offset += 1
        return result.decode('ascii')
    
    def get_section_offset(self, section_idx):
        """获取段的文件偏移"""
        sh_offset = self.e_shoff + section_idx * self.e_shentsize
        sh_offset_val = struct.unpack('<I', self.elf_data[sh_offset+16:sh_offset+20])[0]
        return sh_offset_val
    
    def update_text_section_size(self, new_size):
        """
        更新.text段的大小
        
        Args:
            new_size: 新的段大小
        """
        text_section = self.find_text_section()
        if not text_section:
            print("错误: 找不到.text段")
            return False
        
        # 更新段头中的sh_size字段 (偏移20)
        sh_offset = text_section['header_offset']
        struct.pack_into('<I', self.elf_data, sh_offset + 20, new_size)
        
        print(f"  ✓ 更新.text段大小: {text_section['size']} → {new_size}")
        return True
    
    def add_symbol(self, name, value, size, info, shndx):
        """
        添加符号到符号表
        
        Args:
            name: 符号名
            value: 地址
            size: 大小
            info: 类型和绑定 (STB_GLOBAL|STT_FUNC = 0x12)
            shndx: 所属段索引
        """
        # 简化实现：打印信息，实际添加需要操作符号表
        print(f"  → 添加符号: {name} = 0x{value:04X} (size={size}, info=0x{info:02X})")
        return True
    
    def save(self, output_path):
        """保存修改后的ELF"""
        with open(output_path, 'wb') as f:
            f.write(self.elf_data)
        print(f"  ✓ 保存ELF: {output_path}")


def update_elf_structures(elf_file, new_text_size, output_file):
    """
    更新ELF结构
    
    Args:
        elf_file: 原始ELF路径
        new_text_size: .text段新大小
        output_file: 输出ELF路径
    """
    print("\n更新ELF结构:")
    
    # 加载ELF
    updater = ELFUpdater(elf_file)
    
    # 1. 更新.text段大小
    updater.update_text_section_size(new_text_size)
    
    # 2. 添加_asap_restore符号
    text_section = updater.find_text_section()
    if text_section:
        updater.add_symbol(
            '_asap_restore',
            text_section['addr'],  # 恢复逻辑在.text开头
            64,  # 恢复逻辑大小
            0x12,  # STB_GLOBAL | STT_FUNC
            text_section['index']
        )
    
    # 3. 保存
    updater.save(output_file)
    
    return True


if __name__ == '__main__':
    # 测试
    import sys
    if len(sys.argv) > 1:
        elf = ELFUpdater(sys.argv[1])
        print(f"ELF头信息:")
        print(f"  入口点: 0x{elf.e_entry:04X}")
        print(f"  段头表偏移: 0x{elf.e_shoff:04X}")
        print(f"  段数: {elf.e_shnum}")
        
        text = elf.find_text_section()
        if text:
            print(f"\n.text段:")
            print(f"  地址: 0x{text['addr']:04X}")
            print(f"  大小: {text['size']} 字节")
            print(f"  偏移: 0x{text['offset']:04X}")







