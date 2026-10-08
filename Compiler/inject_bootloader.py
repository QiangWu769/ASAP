#!/usr/bin/env python3
"""
将bootloader.s复制到build目录

bootloader应该作为单独的汇编文件编译，然后链接到主程序
"""

import argparse
import shutil
from pathlib import Path

def copy_bootloader(bootloader_path: str, output_path: str):
    """复制bootloader汇编文件到build目录"""
    
    # 复制bootloader文件
    shutil.copy2(bootloader_path, output_path)
    
    print(f"[copy_bootloader] 成功复制bootloader到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description="复制bootloader汇编文件到build目录")
    parser.add_argument("--bootloader", default="Runtime/bootloader.s", 
                       help="bootloader汇编文件")
    parser.add_argument("--output", default="build/bootloader.s", 
                       help="输出文件")
    
    args = parser.parse_args()
    
    copy_bootloader(args.bootloader, args.output)

if __name__ == "__main__":
    main()