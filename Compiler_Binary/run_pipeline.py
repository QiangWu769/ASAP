#!/usr/bin/env python3
"""
ASAP 二进制级状态保护 — 完整 12 Stage 编译流水线
用途：在终端一次性输出所有 Stage 的详细信息，适合论文截图
运行：python3 run_pipeline.py [源文件路径]
"""

import subprocess, sys, os, time

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(SCRIPT_DIR)
SOURCE_DEFAULT = os.path.join(PROJECT_ROOT, "Benchmarks/ar/main_ar.c")
OUTPUT_DIR     = os.path.join(PROJECT_ROOT, "build_binary")
GCC            = "msp430-elf-gcc"
MCU            = "msp430fr5969"

W = 70

stage_records = []


def hline(char="─"):
    return char * W


def banner(stage_num, total, title):
    n = f"Stage {stage_num}/{total}"
    print(f"\n{'━' * W}")
    print(f"  ┃  {n}  ┃  {title}")
    print(f"{'━' * W}")


def ok(msg):
    print(f"  ✓ {msg}")


def fail(msg):
    print(f"  ✗ {msg}")
    sys.exit(1)


def info(label, value):
    print(f"  {label:<16s}{value}")


def run_py(script, args):
    """直接在当前进程中执行子脚本，避免 subprocess 开销。"""
    script_path = os.path.join(SCRIPT_DIR, script) if not os.path.isabs(script) else script
    saved_argv = sys.argv[:]
    sys.argv = [script_path] + args
    saved_cwd = os.getcwd()
    os.chdir(SCRIPT_DIR)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("__main__", script_path)
        mod = importlib.util.module_from_spec(spec)
        mod.__name__ = "__main__"
        spec.loader.exec_module(mod)
    except SystemExit as e:
        if e.code and e.code != 0:
            fail(f"脚本 {script} 退出码 {e.code}")
    except Exception as e:
        fail(f"脚本 {script} 异常: {e}")
    finally:
        sys.argv = saved_argv
        os.chdir(saved_cwd)


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"命令失败: {cmd}\n    {result.stderr.strip()}")
    return result


def fsize(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def flines(path):
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def stage_start(num, total, title):
    banner(num, total, title)
    return time.time()


def stage_end(num, title, t0, key_output=""):
    elapsed = time.time() - t0
    print(f"\n  [OK] Stage {num} 完成  [{elapsed:.1f}s]")
    if key_output:
        print(f"       -> {key_output}")
    stage_records.append((num, title, elapsed, key_output))


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE_DEFAULT
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    T = 12
    t_total = time.time()

    # 不输出总标题和概览，直接进入各 Stage

    # ── Stage 1 ────────────────────────────────────────────────────
    t0 = stage_start(1, T, "源文件编译")
    info("优化级别:", "-O0（无优化，保留完整调试信息）")
    info("调试信息:", "-g（DWARF 格式）")
    print()

    elf = f"{OUTPUT_DIR}/original.elf"
    print("  [1/3] 编译中...")
    run_cmd(f'{GCC} -mmcu={MCU} -O0 -g "{source}" -o {elf}')
    ok("编译成功")

    print("\n  [2/3] 统计源文件信息...")
    src_lines = flines(source)
    src_size  = fsize(source)
    info("源文件行数:", f"{src_lines:,}")
    info("源文件大小:", f"{src_size:,} 字节")

    print("\n  [3/3] 统计编译输出...")
    elf_size = fsize(elf)
    info("输出文件:", elf)
    info("ELF 大小:", f"{elf_size:,} 字节")
    stage_end(1, "源文件编译", t0, elf)

    # ── Stage 2 ────────────────────────────────────────────────────
    t0 = stage_start(2, T, ".text 段提取")
    run_py("stage2_extract_text.py", [
        f"{OUTPUT_DIR}/original.elf",
        "--output-dir", OUTPUT_DIR,
    ])
    stage_end(2, ".text段提取", t0, f"{OUTPUT_DIR}/text_section.bin")

    # ── Stage 3 ────────────────────────────────────────────────────
    t0 = stage_start(3, T, "指令解码")
    run_py("stage3_disassemble.py", [
        f"{OUTPUT_DIR}/text_section.bin",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/instructions.json",
    ])
    stage_end(3, "指令解码", t0, f"{OUTPUT_DIR}/instructions.json")

    # ── Stage 4 ────────────────────────────────────────────────────
    t0 = stage_start(4, T, "关键写操作识别")
    run_py("stage4_analyze_writes.py", [
        f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/candidates.json",
    ])
    stage_end(4, "关键写操作识别", t0, f"{OUTPUT_DIR}/candidates.json")

    # ── Stage 5 ────────────────────────────────────────────────────
    t0 = stage_start(5, T, "FRAM 槽位分配")
    run_py("stage5_allocate_fram.py", [
        f"{OUTPUT_DIR}/candidates.json",
        "--output", f"{OUTPUT_DIR}/fram_slots.json",
    ])
    stage_end(5, "FRAM槽位分配", t0, f"{OUTPUT_DIR}/fram_slots.json")

    # ── Stage 6 ────────────────────────────────────────────────────
    t0 = stage_start(6, T, "备份序列生成")
    run_py("stage6_generate_backup_code.py", [
        f"{OUTPUT_DIR}/candidates.json",
        "--fram-slots", f"{OUTPUT_DIR}/fram_slots.json",
        "--output", f"{OUTPUT_DIR}/backup_patches.json",
    ])
    stage_end(6, "备份序列生成", t0, f"{OUTPUT_DIR}/backup_patches.json")

    # ── Stage 7 ────────────────────────────────────────────────────
    t0 = stage_start(7, T, "备份插桩")
    run_py("stage7_patch_binary.py", [
        f"{OUTPUT_DIR}/text_section.bin",
        "--patches", f"{OUTPUT_DIR}/backup_patches.json",
        "--instructions", f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/text_instrumented.bin",
    ])
    stage_end(7, "备份插桩", t0, f"{OUTPUT_DIR}/text_instrumented.bin")

    # ── Stage 8 ────────────────────────────────────────────────────
    t0 = stage_start(8, T, "备份点-PC 映射提取")
    run_py("stage8_extract_wid_pc.py", [
        f"{OUTPUT_DIR}/text_instrumented.bin",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--output", f"{OUTPUT_DIR}/wid_pc_map.json",
    ])
    stage_end(8, "备份点-PC映射", t0, f"{OUTPUT_DIR}/wid_pc_map.json")

    # ── Stage 9 ────────────────────────────────────────────────────
    t0 = stage_start(9, T, "调用图构建")
    run_py("stage9_build_call_graph.py", [
        f"{OUTPUT_DIR}/instructions.json",
        "--section-info", f"{OUTPUT_DIR}/section_info.json",
        "--output", f"{OUTPUT_DIR}/call_graph.json",
    ])
    stage_end(9, "调用图构建", t0, f"{OUTPUT_DIR}/call_graph.json")

    # ── Stage 10 ───────────────────────────────────────────────────
    t0 = stage_start(10, T, "状态生命周期分析")
    run_py("stage10_state_liveness_complete.py", [
        "--instructions", f"{OUTPUT_DIR}/instructions.json",
        "--call-graph", f"{OUTPUT_DIR}/call_graph.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--wid-pc-map", f"{OUTPUT_DIR}/wid_pc_map.json",
        "--output", f"{OUTPUT_DIR}/recovery_sets.json",
    ])
    stage_end(10, "状态生命周期分析", t0, f"{OUTPUT_DIR}/recovery_sets.json")

    # ── Stage 11 ───────────────────────────────────────────────────
    t0 = stage_start(11, T, "重建逻辑生成")
    run_py("stage11_generate_restore_binary.py", [
        "--wid-pc-map", f"{OUTPUT_DIR}/wid_pc_map.json",
        "--candidates", f"{OUTPUT_DIR}/candidates.json",
        "--fram-slots", f"{OUTPUT_DIR}/fram_slots.json",
        "--output", f"{OUTPUT_DIR}/restore_logic.bin",
    ])
    stage_end(11, "重建逻辑生成", t0, f"{OUTPUT_DIR}/restore_logic.bin")

    # ── Stage 12 ───────────────────────────────────────────────────
    t0 = stage_start(12, T, "固件重链接")
    run_py("stage12_relink.py", [
        "--restore-logic", f"{OUTPUT_DIR}/restore_logic.bin",
        "--instrumented", f"{OUTPUT_DIR}/text_instrumented.bin",
        "--original-elf", f"{OUTPUT_DIR}/original.elf",
        "--output", f"{OUTPUT_DIR}/firmware_final.elf",
    ])
    stage_end(12, "固件重链接", t0, f"{OUTPUT_DIR}/firmware_final.elf")

    # ── 总结 ───────────────────────────────────────────────────────
    elapsed_total = time.time() - t_total

    print(f"\n\n{'━' * W}")
    print(f"  全部 12 个 Stage 执行完成")
    print(f"{'━' * W}")

    print(f"\n  ┌{'─' * 8}┬{'─' * 22}┬{'─' * 10}┬{'─' * 24}┐")
    print(f"  │{'Stage':^8s}│{'名称':^20s}│{'耗时':^8s}│{'关键产出':^22s}│")
    print(f"  ├{'─' * 8}┼{'─' * 22}┼{'─' * 10}┼{'─' * 24}┤")
    for num, title, sec, output in stage_records:
        fname = os.path.basename(output) if output else ""
        print(f"  │{num:^8d}│ {title:<20s}│{sec:>7.1f}s │ {fname:<22s}│")
    print(f"  └{'─' * 8}┴{'─' * 22}┴{'─' * 10}┴{'─' * 24}┘")

    orig_text  = fsize(f"{OUTPUT_DIR}/text_section.bin")
    instr_text = fsize(f"{OUTPUT_DIR}/text_instrumented.bin")
    restore    = fsize(f"{OUTPUT_DIR}/restore_logic.bin")
    final      = fsize(f"{OUTPUT_DIR}/firmware_final.elf")

    print(f"\n  {'─' * W}")
    print(f"  固件体积对比")
    print(f"  {'─' * W}")
    info("原始 .text:",    f"{orig_text:,} 字节")
    info("插桩后 .text:",  f"{instr_text:,} 字节  (+{instr_text - orig_text:,}B, "
                           f"+{(instr_text - orig_text) / orig_text * 100:.1f}%)")
    info("恢复逻辑:",      f"{restore:,} 字节")
    info("最终固件:",      f"{final:,} 字节")

    print(f"\n  {'─' * W}")
    info("总耗时:", f"{elapsed_total:.1f} 秒")
    info("输入:", source)
    info("输出:", f"{OUTPUT_DIR}/firmware_final.elf")
    print()


if __name__ == "__main__":
    main()
