#!/usr/bin/env python3
"""
ASAP LLVM IR 管线 — 完整编译流水线

流程:
  Stage 1: clang → .ll (LLVM IR)
  Stage 2: 解析 IR (函数/store/alloca/call)
  Stage 3: 识别关键写操作
  Stage 4: FRAM 槽位分配
  Stage 5: IR 插桩 (插入备份 store)
  Stage 6: 调用图构建
  Stage 7: 生命周期分析
  Stage 8: 恢复逻辑生成 (MSP430 汇编)
  Stage 9: 编译: 插桩 IR → .s → .o
  Stage 10: 编译恢复逻辑 → .o
  Stage 11: 链接最终固件

用法:
  python3 run_llvm_pipeline.py Benchmarks/ar/main_ar.c
  python3 run_llvm_pipeline.py --compiler msp430-elf-gcc my_program.c
"""

import subprocess
import sys
import os
import time
import argparse
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

CLANG = '/opt/homebrew/opt/llvm/bin/clang'
LLC = '/opt/homebrew/opt/llvm/bin/llc'
GCC = 'msp430-elf-gcc'
MCU = 'msp430fr5969'
MSP430_INCLUDE = '/opt/local/msp430-elf/include'

W = 70


def banner(stage_num, total, title):
    print(f"\n{'━' * W}")
    print(f"  ┃  Stage {stage_num}/{total}  ┃  {title}")
    print(f"{'━' * W}")


def run_cmd(cmd, desc=''):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ 失败: {desc}")
        print(f"    {result.stderr.strip()}")
        sys.exit(1)
    return result


def run_py(script, args_list):
    script_path = os.path.join(SCRIPT_DIR, script)
    cmd = f'python3 "{script_path}" ' + ' '.join(f'"{a}"' for a in args_list)
    return run_cmd(cmd, script)


def fsize(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def main():
    ap = argparse.ArgumentParser(description='ASAP LLVM IR 管线')
    ap.add_argument('source', help='C 源文件路径')
    ap.add_argument('--output-dir', default=None, help='输出目录')
    ap.add_argument('--gcc', default=GCC, help='MSP430 GCC 路径')
    ap.add_argument('--clang', default=CLANG, help='Clang 路径')
    ap.add_argument('--config', default=None, help='排除配置 JSON')
    args = ap.parse_args()

    source = os.path.abspath(args.source)
    out_dir = args.output_dir or os.path.join(PROJECT_ROOT, 'build_llvm')
    os.makedirs(out_dir, exist_ok=True)

    config_arg = ''
    if args.config:
        config_arg = f'--config "{args.config}"'

    T = 11
    t_total = time.time()

    print(f"{'━' * W}")
    print(f"  ASAP LLVM IR 管线")
    print(f"  源文件: {source}")
    print(f"  输出:   {out_dir}")
    print(f"{'━' * W}")

    # ── Stage 1: clang → .ll ───────────────────────────────────
    banner(1, T, 'C 源码 → LLVM IR')
    ll_file = os.path.join(out_dir, 'program.ll')
    # 获取源文件目录用于 include
    src_dir = os.path.dirname(source)
    include_flags = (
        f'-I"{MSP430_INCLUDE}" '
        f'-I"{src_dir}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/ar")}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/ar/libio")}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/ar/libedb")}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/ar/libmsp")}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/bc")}" '
        f'-I"{os.path.join(PROJECT_ROOT, "Benchmarks/bc/libio")}" '
    )
    run_cmd(
        f'"{args.clang}" --target=msp430 -S -emit-llvm -O0 '
        f'-D__MSP430FR5969__ '
        f'-D\'__delay_cycles(x)=((void)0)\' '
        f'{include_flags} '
        f'"{source}" -o "{ll_file}"',
        'clang → IR'
    )
    ll_lines = sum(1 for _ in open(ll_file))
    print(f"  ✓ IR 生成: {ll_file} ({ll_lines} 行)")

    # ── Stage 2: 解析 IR ───────────────────────────────────────
    banner(2, T, '解析 LLVM IR')
    ir_json = os.path.join(out_dir, 'ir_parsed.json')
    run_py('parse_llvm_ir.py', [ll_file, '-o', ir_json])

    # ── Stage 3: 识别关键写 ───────────────────────────────────
    banner(3, T, '识别关键写操作')
    candidates_json = os.path.join(out_dir, 'candidates.json')
    cmd_args = [ir_json, '-o', candidates_json]
    if args.config:
        cmd_args += ['--config', args.config]
    run_py('analyze_stores.py', cmd_args)

    # ── Stage 4: FRAM 槽位分配 ────────────────────────────────
    banner(4, T, 'FRAM 槽位分配')
    fram_slots_json = os.path.join(out_dir, 'fram_slots.json')
    run_py('allocate_fram.py', [candidates_json, '-o', fram_slots_json])

    # ── Stage 5: IR 插桩 ──────────────────────────────────────
    banner(5, T, 'IR 插桩 — 插入备份 store')
    ll_instrumented = os.path.join(out_dir, 'program_instrumented.ll')
    run_py('instrument_ir.py', [
        ll_file,
        '--candidates', candidates_json,
        '--fram-slots', fram_slots_json,
        '-o', ll_instrumented,
    ])

    # ── Stage 6: 调用图 ──────────────────────────────────────
    banner(6, T, '构建函数调用图')
    call_graph_json = os.path.join(out_dir, 'call_graph.json')
    run_py('build_call_graph_ir.py', [ir_json, '-o', call_graph_json])

    # ── Stage 7: 生命周期分析 ─────────────────────────────────
    banner(7, T, '状态生命周期分析')
    recovery_json = os.path.join(out_dir, 'recovery_sets.json')
    run_py('liveness_ir.py', [
        '--ir-json', ir_json,
        '--candidates', candidates_json,
        '--call-graph', call_graph_json,
        '-o', recovery_json,
    ])

    # ── Stage 8: 恢复逻辑生成 ────────────────────────────────
    banner(8, T, '恢复逻辑生成 (MSP430 汇编)')
    restore_asm = os.path.join(out_dir, 'asap_restore.s')
    run_py('generate_restore_ir.py', [
        '--recovery-sets', recovery_json,
        '--fram-slots', fram_slots_json,
        '--candidates', candidates_json,
        '-o', restore_asm,
    ])

    # ── Stage 9: 编译插桩 IR → .o ────────────────────────────
    banner(9, T, '编译插桩 IR → 目标文件')
    main_s = os.path.join(out_dir, 'program.s')
    main_o = os.path.join(out_dir, 'program.o')

    # IR → 汇编
    run_cmd(
        f'"{LLC}" -march=msp430 -O0 "{ll_instrumented}" -o "{main_s}"',
        'llc → assembly'
    )
    print(f"  ✓ 汇编: {main_s} ({fsize(main_s)} bytes)")

    # 汇编 → 目标文件
    run_cmd(
        f'"{args.gcc}" -mmcu={MCU} -c "{main_s}" -o "{main_o}"',
        'gcc → object'
    )
    print(f"  ✓ 目标文件: {main_o}")

    # ── Stage 10: 编译恢复逻辑 ────────────────────────────────
    banner(10, T, '编译恢复逻辑')
    restore_o = os.path.join(out_dir, 'asap_restore.o')
    run_cmd(
        f'"{args.gcc}" -mmcu={MCU} -c "{restore_asm}" -o "{restore_o}"',
        'gcc → restore object'
    )
    print(f"  ✓ 恢复逻辑: {restore_o}")

    # ── Stage 11: 链接最终固件 ────────────────────────────────
    banner(11, T, '链接最终固件')
    linker_script = os.path.join(PROJECT_ROOT,
                                  'Runtime/src/port/msp430/msp430fr5969_bootloader.ld')
    bootloader_s = os.path.join(PROJECT_ROOT, 'Runtime/bootloader_with_restore.s')
    bootloader_o = os.path.join(out_dir, 'bootloader.o')
    firmware_out = os.path.join(out_dir, 'firmware_llvm.out')

    # 编译 bootloader
    if os.path.exists(bootloader_s):
        run_cmd(
            f'"{args.gcc}" -mmcu={MCU} -c "{bootloader_s}" -o "{bootloader_o}"',
            'bootloader'
        )
        # 链接
        run_cmd(
            f'"{args.gcc}" -mmcu={MCU} -nostartfiles '
            f'-T "{linker_script}" '
            f'-o "{firmware_out}" '
            f'"{bootloader_o}" "{main_o}" "{restore_o}" -lgcc',
            'final link'
        )
    else:
        # 无 bootloader 时简单链接
        run_cmd(
            f'"{args.gcc}" -mmcu={MCU} '
            f'-o "{firmware_out}" '
            f'"{main_o}" "{restore_o}" -lgcc',
            'final link (no bootloader)'
        )

    print(f"  ✓ 最终固件: {firmware_out} ({fsize(firmware_out)} bytes)")

    # ── 总结 ───────────────────────────────────────────────────
    elapsed = time.time() - t_total
    print(f"\n{'━' * W}")
    print(f"  ASAP LLVM IR 管线完成")
    print(f"{'━' * W}")
    print(f"  源文件:  {source}")
    print(f"  IR:      {ll_file} ({ll_lines} 行)")
    print(f"  固件:    {firmware_out} ({fsize(firmware_out):,} bytes)")
    print(f"  总耗时:  {elapsed:.1f} 秒")
    print(f"{'━' * W}")


if __name__ == '__main__':
    main()
