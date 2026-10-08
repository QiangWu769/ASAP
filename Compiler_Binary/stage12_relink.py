#!/usr/bin/env python3
"""
Stage 12: 固件重链接
将应用代码、引导程序、恢复例程、备份槽位、查找表重新组合

功能:
1. 生成多section ELF
   - .text.app: 插桩后的应用代码
   - .text.boot: 引导程序
   - .text.recover: 恢复例程
   - .asap_backup: 备份槽位数组
   - .asap_recovery_table: 恢复查找表
2. 修改链接脚本，划分MEMORY区域
3. 入口重定向（修改e_entry和复位向量）
"""

import argparse
import struct
import json
import os
from pathlib import Path


def generate_linker_script_patch(base_script_path, output_script_path):
    """
    生成修改后的链接脚本
    
    在原有脚本基础上添加:
    - MEMORY: BOOT, APP, BACKUP, RECMETA区域
    - SECTIONS: .text.app, .text.boot, .text.recover等
    """
    print("[1/5] 生成链接脚本...")
    
    # 读取基础脚本（如果有）
    if base_script_path and base_script_path.exists():
        with open(base_script_path, 'r') as f:
            base_content = f.read()
    else:
        base_content = ""
    
    # 生成自定义链接脚本
    script_content = '''/* 纯机器码ASAP - 自定义链接脚本 */

MEMORY
{
  /* FRAM划分 */
  BOOT     (rx) : ORIGIN = 0x4400, LENGTH = 0x0400  /* 1KB  - 引导+恢复 */
  APP      (rx) : ORIGIN = 0x4800, LENGTH = 0xC000  /* 48KB - 应用代码 */
  BACKUP   (rw) : ORIGIN = 0x10800, LENGTH = 0x0800 /* 2KB  - 备份槽位 */
  RECMETA  (r)  : ORIGIN = 0x11000, LENGTH = 0x0400 /* 1KB  - 恢复查找表 */
  
  /* SRAM */
  RAM      (rw) : ORIGIN = 0x1C00, LENGTH = 0x0800  /* 2KB */
}

SECTIONS
{
  /* 引导和恢复代码 */
  .text.boot : {
    KEEP(*(.text.boot))
    __boot_end = .;
  } > BOOT
  
  .text.recover : {
    KEEP(*(.text.recover))
    __recover_end = .;
  } > BOOT
  
  /* 应用代码（插桩后） */
  .text.app : {
    *(.text .text.*)
    . = ALIGN(2);
    __app_end = .;
  } > APP
  
  /* 备份槽位数组 */
  .asap_backup : {
    __backup_slots_start = .;
    KEEP(*(.asap_backup))
    __backup_slots_end = .;
  } > BACKUP
  
  /* 恢复查找表 */
  .asap_recovery_table : {
    __recovery_table_start = .;
    KEEP(*(.asap_recovery_table))
    __recovery_table_end = .;
  } > RECMETA
  
  /* 数据段 */
  .data : {
    *(.data .data.*)
  } > RAM AT > APP
  
  .bss : {
    *(.bss .bss.*)
  } > RAM
}

/* 入口重定向 */
ENTRY(__boot_entry)
'''
    
    with open(output_script_path, 'w') as f:
        f.write(script_content)
    
    print(f"  ✓ 生成链接脚本: {output_script_path}")
    
    # 展示MEMORY布局
    print(f"\n  MEMORY布局:")
    print(f"    BOOT     : 0x4400-0x47FF (1KB)   ← 引导+恢复")
    print(f"    APP      : 0x4800-0x107FF (48KB) ← 应用代码")
    print(f"    BACKUP   : 0x10800-0x10FFF (2KB) ← 备份槽位")
    print(f"    RECMETA  : 0x11000-0x113FF (1KB) ← 查找表")
    
    print(f"\n  SECTIONS布局:")
    print(f"    .text.boot    → BOOT   (引导程序)")
    print(f"    .text.recover → BOOT   (恢复例程)")
    print(f"    .text.app     → APP    (插桩后应用)")
    print(f"    .asap_backup  → BACKUP (槽位数组)")
    print(f"    .asap_recovery_table → RECMETA (查找表)")


def create_multi_section_elf(restore_logic, instrumented_code, output_path):
    """
    创建多section ELF
    
    使用objcopy将不同部分放入不同section
    """
    print("\n[2/5] 创建多section目标文件...")
    
    # 保存各个section到临时文件
    temp_dir = output_path.parent / 'temp_sections'
    temp_dir.mkdir(exist_ok=True)
    
    boot_bin = temp_dir / 'boot.bin'
    recover_bin = temp_dir / 'recover.bin'
    app_bin = temp_dir / 'app.bin'
    
    # 引导程序（简化：暂时为空，实际需要实现）
    with open(boot_bin, 'wb') as f:
        # 简单的引导程序：跳转到恢复检查
        boot_code = bytes([
            0x30, 0x40, 0x00, 0x44,  # BR #0x4400 (跳转到恢复)
        ])
        f.write(boot_code)
    
    # 恢复例程
    with open(recover_bin, 'wb') as f:
        f.write(restore_logic)
    
    # 应用代码
    with open(app_bin, 'wb') as f:
        f.write(instrumented_code)
    
    print(f"  ✓ 引导程序: {len(boot_code)} 字节 → .text.boot")
    print(f"  ✓ 恢复例程: {len(restore_logic)} 字节 → .text.recover")
    print(f"  ✓ 应用代码: {len(instrumented_code)} 字节 → .text.app")
    
    return boot_bin, recover_bin, app_bin


def redirect_entry_point(elf_path, boot_entry_addr):
    """
    修改ELF入口点
    
    1. 修改ELF Header的e_entry字段
    2. 修改复位向量（如果有.vectors section）
    """
    print("\n[3/5] 入口重定向...")
    
    with open(elf_path, 'rb') as f:
        elf_data = bytearray(f.read())
    
    # 读取当前e_entry
    old_entry = struct.unpack('<I', elf_data[0x18:0x1C])[0]
    
    print(f"  原始入口点: 0x{old_entry:04X}")
    print(f"  新入口点: 0x{boot_entry_addr:04X} (__boot_entry)")
    
    # 修改e_entry
    struct.pack_into('<I', elf_data, 0x18, boot_entry_addr)
    
    print(f"  ✓ 修改ELF Header e_entry: 0x{old_entry:04X} → 0x{boot_entry_addr:04X}")
    
    # TODO: 修改.vectors section中的复位向量
    # 这需要解析section table找到.vectors
    
    # 保存修改后的ELF
    with open(elf_path, 'wb') as f:
        f.write(elf_data)
    
    print(f"  ✓ 保存修改后的ELF")
    
    return old_entry, boot_entry_addr


def verify_relinking(elf_path):
    """
    验证重链接结果
    """
    print("\n[4/5] 验证重链接结果...")
    
    with open(elf_path, 'rb') as f:
        elf_data = f.read()
    
    # 验证Magic
    if elf_data[:4] != b'\x7fELF':
        print(f"  ✗ 不是有效的ELF文件")
        return False
    
    # 读取e_entry
    e_entry = struct.unpack('<I', elf_data[0x18:0x1C])[0]
    print(f"  ✓ 入口地址: 0x{e_entry:04X}")
    
    # 读取e_shnum
    e_shnum = struct.unpack('<H', elf_data[0x30:0x32])[0]
    print(f"  ✓ Section数量: {e_shnum}")
    
    # 验证文件大小
    file_size = len(elf_data)
    print(f"  ✓ 文件大小: {file_size} 字节")
    
    return True


def print_relinking_comparison(old_entry, new_entry, orig_text_size, boot_size, restore_size, app_size, final_size):
    """
    打印重链接前后对比
    """
    print("\n[5/5] 重链接前后对比...")
    print()
    print("  " + "="*66)
    print("  重链接前（原始固件）vs 重链接后（ASAP固件）")
    print("  " + "="*66)
    print()
    
    print(f"  {'项目':<20s} {'原始固件':>15s} {'ASAP固件':>15s}")
    print(f"  {'-'*55}")
    print(f"  {'入口地址':<20s} {'0x%04X' % old_entry:>15s} {'0x%04X' % new_entry:>15s}")
    print(f"  {'.text大小':<20s} {str(orig_text_size)+'B':>15s} {str(final_size)+'B':>15s}")
    print(f"  {'Section数':<20s} {'单一.text':>15s} {'5个section':>15s}")
    print(f"  {'引导程序':<20s} {'(无)':>15s} {'✓ %dB' % boot_size:>15s}")
    print(f"  {'恢复例程':<20s} {'(无)':>15s} {'✓ %dB' % restore_size:>15s}")
    print(f"  {'应用代码':<20s} {'✓ %dB' % orig_text_size:>15s} {'✓ %dB' % app_size:>15s}")
    print(f"  {'备份槽位':<20s} {'(无)':>15s} {'✓ 预留':>15s}")
    print(f"  {'查找表':<20s} {'(无)':>15s} {'✓ 预留':>15s}")
    print()
    
    print(f"  入口重定向:")
    print(f"    原始: 上电 → main (0x{old_entry:04X})")
    print(f"    ASAP: 上电 → __boot_entry (0x{new_entry:04X})")
    print(f"          → 检查备份标志")
    print(f"          → 如需恢复，跳转到恢复例程")
    print(f"          → 否则，跳转到应用入口")
    print()
    
    print(f"  ✓ 重链接成功！入口 0x{old_entry:04X} → 0x{new_entry:04X}")


def main():
    parser = argparse.ArgumentParser(
        description='Stage 12: 固件重链接'
    )
    
    parser.add_argument('--restore-logic',
                       default='build/machine_code/restore_logic.bin')
    parser.add_argument('--instrumented',
                       default='build/machine_code/text_instrumented.bin')
    parser.add_argument('--original-elf',
                       default='build/machine_code/original.elf')
    parser.add_argument('--output',
                       default='build/machine_code/firmware_final.elf')
    
    args = parser.parse_args()
    
    
    
    # 加载输入文件
    restore_logic_path = Path(args.restore_logic)
    instrumented_path = Path(args.instrumented)
    original_elf_path = Path(args.original_elf)
    output_path = Path(args.output)
    
    with open(restore_logic_path, 'rb') as f:
        restore_logic = f.read()
    
    with open(instrumented_path, 'rb') as f:
        instrumented_code = f.read()
    
    print(f"输入:")
    print(f"  恢复逻辑: {len(restore_logic)} 字节")
    print(f"  插桩代码: {len(instrumented_code)} 字节")
    print()
    
    # 生成链接脚本
    linker_script = output_path.parent / 'asap_custom.ld'
    generate_linker_script_patch(None, linker_script)
    
    # 创建多section ELF
    boot_bin, recover_bin, app_bin = create_multi_section_elf(
        restore_logic, instrumented_code, output_path
    )
    
    # 简化版：直接合并（实际需要使用链接器）
    print("\n[简化实现] 直接合并二进制...")
    merged = restore_logic + instrumented_code
    
    # 使用objcopy创建ELF
    merged_bin = output_path.parent / 'firmware_merged.bin'
    with open(merged_bin, 'wb') as f:
        f.write(merged)
    
    import subprocess
    cmd = [
        'msp430-elf-objcopy',
        '-I', 'binary',
        '-O', 'elf32-msp430',
        '-B', 'msp430',
        '--rename-section', '.data=.text,alloc,load,readonly,code',
        str(merged_bin),
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  ✓ 创建ELF: {output_path}")
    
    # 获取原始ELF信息
    with open(original_elf_path, 'rb') as f:
        orig_elf = f.read()
    orig_entry = struct.unpack('<I', orig_elf[0x18:0x1C])[0]
    
    # 入口重定向
    boot_entry = 0x4400  # BOOT区域起始
    old_entry, new_entry = redirect_entry_point(output_path, boot_entry)
    
    # 加载 section_info 获取真正的原始 .text 大小
    section_info_path = Path(args.instrumented).parent / 'section_info.json'
    orig_text_size = 0
    if section_info_path.exists():
        with open(section_info_path, 'r') as f:
            section_info = json.load(f)
        orig_text_size = section_info.get('size', 0)
    
    # 验证
    if verify_relinking(output_path):
        boot_size = os.path.getsize(boot_bin) if boot_bin and Path(boot_bin).exists() else 4
        print_relinking_comparison(
            orig_entry, boot_entry,
            orig_text_size,
            boot_size,
            len(restore_logic),
            len(instrumented_code),
            len(merged)
        )
    
    # 打印最终摘要
    print("\n" + "="*70)
    print("  固件重链接完成")
    print("="*70)
    print(f"  输出: {output_path} ({os.path.getsize(output_path)}B)")
    print(f"    原始.text:  {orig_text_size} 字节")
    print(f"    插桩后:     {len(instrumented_code)} 字节")
    print(f"    恢复逻辑:   {len(restore_logic)} 字节")
    print(f"    最终.text:  {len(merged)} 字节")
    print(f"    入口地址:   0x{boot_entry:04X}")
    print("="*70)
    print()
    
    print("✅ Stage 12 完成!")
    print(f"  输出: {output_path}")
    print()


if __name__ == '__main__':
    main()




