#!/usr/bin/env python3
"""
编译带bootloader的ASAP程序

使用专门的链接器脚本，将bootloader设置为入口点
"""

import subprocess
import argparse
from pathlib import Path

def compile_with_bootloader(asm_file: str, output_file: str, linker_script: str):
    """编译带bootloader的汇编文件"""
    
    # MSP430编译命令（与Makefile保持一致）
    cmd = [
        "msp430-elf-gcc",  # 与Makefile中的COMPILER变量保持一致
        "-mmcu=msp430fr5969",
        "-T", linker_script,
        "-o", output_file,
        asm_file
    ]
    
    print(f"[compile_with_bootloader] 编译命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"[compile_with_bootloader] 编译成功: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[compile_with_bootloader] 编译失败:")
        print(f"  错误代码: {e.returncode}")
        print(f"  标准输出: {e.stdout}")
        print(f"  标准错误: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"[compile_with_bootloader] 错误: 未找到msp430-elf-gcc编译器")
        print(f"  请确保MSP430工具链已安装并在PATH中")
        return False

def main():
    parser = argparse.ArgumentParser(description="编译带bootloader的ASAP程序")
    parser.add_argument("--asm", default="build/A_with_bootloader.s", 
                       help="带bootloader的汇编文件")
    parser.add_argument("--output", default="build/asap_firmware.elf", 
                       help="输出ELF文件")
    parser.add_argument("--linker", default="Runtime/linker/msp430fr_ASAP.ld", 
                       help="链接器脚本")
    
    args = parser.parse_args()
    
    success = compile_with_bootloader(args.asm, args.output, args.linker)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
