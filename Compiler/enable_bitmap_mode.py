#!/usr/bin/env python3
"""
位图模式包装脚本
在现有编译流程完成后，添加位图功能
完全不修改现有stages，只在输出上追加

使用流程：
1. 先运行标准编译流程（make）
2. 运行此脚本启用位图模式
3. 重新链接生成最终固件

或者：
  make SRC=xxx.c OUTPUT=xxx.out
  python3 Compiler/enable_bitmap_mode.py --build-dir build
  make stage13  # 重新链接
"""

import json
import argparse
import subprocess
from pathlib import Path


def run_bitmap_pipeline(build_dir):
    """
    执行位图扩展流程
    
    流程：
    1. 检测数组访问
    2. 分配位图结构
    3. 更新备份代码（如果需要重新生成）
    4. 更新恢复代码
    """
    
    build_path = Path(build_dir)
    
    # 检查必需文件
    required_files = [
        'A_idempotent.s',
        'candidates.json',
        'fram_slots.json',
        'fram_symbols.ld'
    ]
    
    for f in required_files:
        if not (build_path / f).exists():
            print(f"  ✗ 缺少文件: {f}")
            print(f"  请先运行标准编译流程")
            return 1
    
    print("\n" + "="*80)
    print("位图模式扩展流程")
    print("="*80)
    
    # 步骤1: 检测数组访问
    print("\n[步骤1] 检测数组访问...")
    cmd = [
        'python3', 'Compiler/detect_array_access.py',
        f'{build_dir}/A_idempotent.s',
        '--candidates', f'{build_dir}/candidates.json',
        '--output', f'{build_dir}/array_detection.json'
    ]
    subprocess.run(cmd, check=True)
    
    # 步骤2: 分配位图结构
    print("\n[步骤2] 分配位图结构...")
    cmd = [
        'python3', 'Compiler/stage4_bitmap_extension.py',
        f'{build_dir}/A_idempotent.s',
        '--candidates', f'{build_dir}/candidates.json',
        '--fram-slots', f'{build_dir}/fram_slots.json',
        '--output-json', f'{build_dir}/fram_slots_bitmap.json',
        '--output-linker', f'{build_dir}/fram_symbols.ld'
    ]
    subprocess.run(cmd, check=True)
    
    # 备份原始文件
    import shutil
    shutil.copy(f'{build_dir}/fram_slots.json', f'{build_dir}/fram_slots_original.json')
    shutil.copy(f'{build_dir}/fram_slots_bitmap.json', f'{build_dir}/fram_slots.json')
    print("  ✓ fram_slots.json 已更新（原始备份到 fram_slots_original.json）")
    
    # 步骤3: 注入位图备份代码
    print("\n[步骤3] 生成位图备份代码...")
    # 检查是否需要重新生成插桩代码
    if (build_path / 'A_instrumented.s').exists():
        print("  ⚠️  已存在 A_instrumented.s")
        print("  位图备份需要重新运行 stage5")
        print("  或者使用现有插桩 + 位图追加（需要实现）")
    else:
        print("  跳过：需要重新运行 stage5")
    
    # 步骤4: 更新恢复代码
    print("\n[步骤4] 追加位图恢复代码...")
    if (build_path / 'asap_restore.s').exists():
        cmd = [
            'python3', 'Compiler/stage11_bitmap_restore.py',
            f'{build_dir}/asap_restore.s'
        ]
        subprocess.run(cmd, check=True)
    else:
        print("  ⚠️  asap_restore.s 不存在，跳过")
    
    print("\n" + "="*80)
    print("位图模式扩展完成")
    print("="*80)
    print("\n下一步：")
    print("  1. 重新运行 make stage5（重新生成插桩代码）")
    print("  2. 继续运行后续stages")
    print("  或者：")
    print("  make SRC=xxx.c OUTPUT=xxx_bitmap.out ENABLE_BITMAP=1")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description='启用位图模式（非侵入式）')
    parser.add_argument('--build-dir', default='build', help='构建目录')
    
    args = parser.parse_args()
    
    return run_bitmap_pipeline(args.build_dir)


if __name__ == '__main__':
    exit(main())















