#!/usr/bin/env python3
"""
ASAP 完整 12 Stage 流水线 — 统一 Python 入口
用途：在终端一次性输出所有 Stage 的详细信息，适合论文截图
运行：python3 run_pipeline_v1.py [源文件路径]
"""

import subprocess
import sys
import os
import shutil
import time

SOURCE_DEFAULT = "../Benchmarks/ar/main_ar.c"
OUTPUT_DIR = "build/machine_code"
GCC = "msp430-elf-gcc"
MCU = "msp430fr5969"

W = 70  # 标题栏宽度


def banner(text, char="═"):
    print(f"\n{char * W}")
    print(f"  {text}")
    print(f"{char * W}")


def section(text, char="─"):
    print(f"\n{char * W}")
    print(f"  {text}")
    print(f"{char * W}")


def ok(msg):
    print(f"  ✓ {msg}")


def info(label, value):
    print(f"  {label:<16s}{value}")


def run_py(script, args, cwd=None):
    """运行 Python 子脚本，将 stdout/stderr 透传到终端。"""
    cmd = [sys.executable, script] + args
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"\n  * 脚本 {script} 返回非零退出码 {result.returncode}")
        sys.exit(1)


def run_cmd(cmd, cwd=None, capture=False):
    """运行 shell 命令。"""
    result = subprocess.run(cmd, shell=True, cwd=cwd,
                            capture_output=capture, text=True)
    if result.returncode != 0:
        print(f"\n  ✗ 命令失败: {cmd}")
        if capture and result.stderr:
            print(f"    {result.stderr.strip()}")
        sys.exit(1)
    return result


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def line_count(path):
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ──────────────────────────────────────────────────────────────────────
#  主流程
# ──────────────────────────────────────────────────────────────────────
def main():
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE_DEFAULT
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    t0 = time.time()

    banner("ASAP 二进制级状态保护 — 完整 12 Stage 编译流水线", "━")
    info("输入源文件:", source)
    info("目标平台:", f"{MCU.upper()}")
    info("编译器:", GCC)
    info("输出目录:", OUTPUT_DIR)
    print()

    # ── Stage 1 ────────────────────────────────────────────────────
    banner("Stage 1 / 12 : 源文件编译")
    info("输入:", source)
    info("优化级别:", "-O0（无优化，保留完整调试信息）")
    info("调试信息:", "-g（DWARF）")
    print()

    print("  [1/3] 编译中...")
    elf = f"{OUTPUT_DIR}/original.elf"
    run_cmd(f'{GCC} -mmcu={MCU} -O0 -g "{source}" -o {elf}')
    ok("编译成功")

    print("\n  [2/3] 统计源文件信息...")
    info("源文件行数:", str(line_count(source)))
    info("源文件大小:", f"{file_size(source)} 字节")

    print("\n  [3/3] 统计编译输出...")
    info("输出文件:", elf)
    info("ELF 大小:", f"{file_size(elf)} 字节")
    print(f"\n  [OK] Stage 1 完成!")

    # ── Stage 2 ────────────────────────────────────────────────────
    banner("Stage 2 / 12 : .text 段提取")
    run_py("stage2_extract_text.py", [
        f"{OUTPUT_DIR}/original.elf",
        "--output-dir", OUTPUT_DIR,
    ])
    print(f"\n  [OK] Stage 2 完成!")

    # ── Stage 3 ────────────────────────────────────────────────────
    banner("Stage 3 / 12 : 指令解码")
    run_py("stage3_disassemble.py", [
        f"{OUTPUT_DIR}/text_section.bin",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/instructions.json",
    ])
    print(f"\n  [OK] Stage 3 完成!")

    # ── Stage 4 ────────────────────────────────────────────────────
    banner("Stage 4 / 12 : 关键写操作识别")
    run_py("stage4_analyze_writes.py", [
        f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/candidates.json",
    ])
    print(f"\n  [OK] Stage 4 完成!")

    # ── Stage 5 ────────────────────────────────────────────────────
    banner("Stage 5 / 12 : FRAM 槽位分配")
    run_py("stage5_allocate_fram.py", [
        f"{OUTPUT_DIR}/candidates.json",
        "--output", f"{OUTPUT_DIR}/fram_slots.json",
    ])
    print(f"\n  [OK] Stage 5 完成!")

    # ── Stage 6 ────────────────────────────────────────────────────
    banner("Stage 6 / 12 : 备份序列生成")
    run_py("stage6_generate_backup_code.py", [
        f"{OUTPUT_DIR}/candidates.json",
        "--fram-slots", f"{OUTPUT_DIR}/fram_slots.json",
        "--output", f"{OUTPUT_DIR}/backup_patches.json",
    ])
    print(f"\n  [OK] Stage 6 完成!")

    # ── Stage 7 ────────────────────────────────────────────────────
    banner("Stage 7 / 12 : 备份插桩")
    run_py("stage7_patch_binary.py", [
        f"{OUTPUT_DIR}/text_section.bin",
        "--patches", f"{OUTPUT_DIR}/backup_patches.json",
        "--instructions", f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/text_instrumented.bin",
    ])
    print(f"\n  [OK] Stage 7 完成!")

    # ── Stage 8 ────────────────────────────────────────────────────
    banner("Stage 8 / 12 : WID-PC 映射提取")
    run_py("stage8_extract_wid_pc.py", [
        f"{OUTPUT_DIR}/text_instrumented.bin",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--output", f"{OUTPUT_DIR}/wid_pc_map.json",
    ])
    print(f"\n  [OK] Stage 8 完成!")

    # ── Stage 9 ────────────────────────────────────────────────────
    banner("Stage 9 / 12 : 调用图构建")
    run_py("stage9_build_call_graph.py", [
        f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/call_graph.json",
    ])
    print(f"\n  [OK] Stage 9 完成!")

    # ── Stage 10 ───────────────────────────────────────────────────
    banner("Stage 10 / 12 : 状态生命周期分析")
    run_py("stage10_state_liveness_complete.py", [
        "--instructions", f"{OUTPUT_DIR}/instructions.json",
        "--call-graph", f"{OUTPUT_DIR}/call_graph.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--wid-pc-map", f"{OUTPUT_DIR}/wid_pc_map.json",
        "--output", f"{OUTPUT_DIR}/recovery_sets.json",
    ])
    print(f"\n  [OK] Stage 10 完成!")

    # ── Stage 11 ───────────────────────────────────────────────────
    banner("Stage 11 / 12 : 重建逻辑生成")
    run_py("stage11_generate_restore_binary.py", [
        "--wid-pc-map", f"{OUTPUT_DIR}/wid_pc_map.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--fram-slots", f"{OUTPUT_DIR}/fram_slots.json",
        "--output", f"{OUTPUT_DIR}/restore_logic.bin",
    ])
    print(f"\n  [OK] Stage 11 完成!")

    # ── Stage 12 ───────────────────────────────────────────────────
    banner("Stage 12 / 12 : 固件重链接")
    run_py("stage12_relink.py", [
        "--restore-logic", f"{OUTPUT_DIR}/restore_logic.bin",
        "--instrumented", f"{OUTPUT_DIR}/text_instrumented.bin",
        "--original-elf", f"{OUTPUT_DIR}/original.elf",
        "--output", f"{OUTPUT_DIR}/firmware_final.elf",
    ])
    print(f"\n  [OK] Stage 12 完成!")

    # ── 总结 ───────────────────────────────────────────────────────
    elapsed = time.time() - t0
    banner("全部 12 个 Stage 执行完成", "━")
    info("总耗时:", f"{elapsed:.1f} 秒")
    info("输入:", source)
    info("最终固件:", f"{OUTPUT_DIR}/firmware_final.elf")
    info("固件大小:", f"{file_size(f'{OUTPUT_DIR}/firmware_final.elf')} 字节")
    print()

    section("输出文件清单")
    outputs = [
        ("original.elf",       "编译产物（原始 ELF）"),
        ("text_section.bin",   ".text 段二进制"),
        ("section_info.json",  "段元数据 + 符号表"),
        ("instructions.json",  "反汇编指令集"),
        ("candidates.json",    "关键写操作候选"),
        ("fram_slots.json",    "FRAM 槽位分配"),
        ("backup_patches.json","备份机器码补丁"),
        ("text_instrumented.bin","插桩后 .text"),
        ("wid_pc_map.json",    "WID → PC 映射表"),
        ("call_graph.json",    "函数调用图"),
        ("recovery_sets.json", "恢复集合 R(pc)"),
        ("restore_logic.bin",  "恢复逻辑机器码"),
        ("firmware_final.elf", "最终固件"),
    ]
    for fname, desc in outputs:
        fpath = f"{OUTPUT_DIR}/{fname}"
        sz = file_size(fpath)
        print(f"  {fname:<30s} {sz:>8,d}B   {desc}")
    print()


if __name__ == "__main__":
    main()
