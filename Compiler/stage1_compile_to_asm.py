#!/usr/bin/env python3
"""
Stage 1: 编译C源码到汇编
输入: C源文件
输出: build/A_sym.s
"""
import argparse
import subprocess
import sys

def compile_to_asm(src_file, output_asm, compiler, mcu, cflags):
    """编译C源码到汇编"""
    cmd = [
        compiler,
        '-S',              # 生成汇编
        '-mmcu=' + mcu,
        src_file,
        '-o', output_asm
    ]
    
    # 添加额外的编译选项
    if cflags:
        cmd.extend(cflags.split())
    
    # 添加包含路径
    import os
    src_dir = os.path.dirname(src_file)
    cmd.extend([
        '-I./' + src_dir,
        '-I./' + src_dir + '/libio',
        '-I./' + src_dir + '/libedb',
        '-I./' + src_dir + '/libmsp',
        '-I./Benchmarks/ar',
        '-I./Benchmarks/ar/libio',
        '-I./Benchmarks/ar/libedb',
        '-I./Benchmarks/ar/libmsp',
        '-I./Benchmarks/bc',
        '-I./Benchmarks/bc/libio',
        '-I./Benchmarks/bc/libedb',
        '-I./Benchmarks/bc/libmsp',
    ])
    
    print(f"  执行: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  ✓ 汇编生成成功: {output_asm}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ 编译失败:")
        print(e.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Stage 1: 编译C到汇编')
    parser.add_argument('src', help='C源文件路径')
    parser.add_argument('--output', default='build/A_sym.s', help='输出汇编文件路径')
    parser.add_argument('--compiler', default='msp430-elf-gcc', help='编译器')
    parser.add_argument('--mcu', default='msp430fr5969', help='目标MCU')
    parser.add_argument('--cflags', default='-O0 -g', help='编译选项')
    
    args = parser.parse_args()
    
    if not compile_to_asm(args.src, args.output, args.compiler, args.mcu, args.cflags):
        sys.exit(1)

if __name__ == '__main__':
    main()





































