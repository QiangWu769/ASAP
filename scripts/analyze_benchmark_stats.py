#!/usr/bin/env python3
"""
Two benchmark-level static analyses:

1. Theoretical restore volume at different execution progress (10%/20%/25%...)
   = cumulative "live state" size that affects subsequent execution

2. Distribution of consecutive register-only instruction sequences
   = sequences where only general-purpose registers are modified (no memory R/W)
"""
import re
import os
import json
from collections import defaultdict, Counter

ASAP_BASE = "/Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本"
BENCHMARKS = {
    "ar": "build_ar_restore/A_sym.s",
    "bc": "build_bc_restore/A_sym.s",
    "cf": "build_cf_restore/A_sym.s",
    "conv": "build/A_sym.s",
    "crc": "build_crc_restore/A_sym.s",
    "adpcm_de": "build_adpcm_restore/A_sym.s",
    "adpcm_en": "build_adpcm_encode_restore/A_sym.s",
}

MSP430_REGS = set(f"R{i}" for i in range(16))
MEMORY_PATTERNS = re.compile(r'@R\d+|[&]|[0-9]+\(R[0-9]+\)|#0x[0-9a-fA-F]+')


def is_register_only(line):
    """Check if an instruction only operates on registers (no memory access)."""
    line = line.strip()
    if not line or line.startswith(';') or line.startswith('.') or line.endswith(':'):
        return False

    parts = line.split(';')[0].strip()
    if not parts:
        return False

    upper = parts.upper()
    mnemonic_match = re.match(r'^(\w+(?:\.\w)?)\s*(.*)', upper)
    if not mnemonic_match:
        return False

    mnemonic = mnemonic_match.group(1)
    operands = mnemonic_match.group(2)

    skip_mnemonics = {'RET', 'RETI', 'NOP', 'JMP', 'JEQ', 'JNE', 'JZ', 'JNZ',
                      'JGE', 'JL', 'JN', 'JC', 'JNC', 'JLO', 'JHS',
                      'CALL', 'BR', 'PUSH', 'POP', 'DINT', 'EINT', 'BIS', 'BIC'}

    base_mnem = mnemonic.split('.')[0]
    if base_mnem in skip_mnemonics:
        return False

    if not operands:
        return False

    has_memory = bool(re.search(r'[&@]|[0-9]+\(R', operands))
    if has_memory:
        return False

    has_imm_or_reg = bool(re.search(r'R\d+|#', operands))
    return has_imm_or_reg


def analyze_reg_only_sequences(asm_lines):
    """Find consecutive register-only instruction sequences and their distribution."""
    seq_lengths = []
    current_seq = 0

    for line in asm_lines:
        if is_register_only(line):
            current_seq += 1
        else:
            if current_seq > 0:
                seq_lengths.append(current_seq)
            current_seq = 0

    if current_seq > 0:
        seq_lengths.append(current_seq)

    counter = Counter(seq_lengths)
    return counter, seq_lengths


def count_memory_writes(asm_lines):
    """Count cumulative memory write instructions at each point."""
    total_instr = 0
    write_points = []
    write_sizes = []

    for i, line in enumerate(asm_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(';') or stripped.startswith('.') or stripped.endswith(':'):
            continue

        upper = stripped.upper().split(';')[0].strip()
        if not upper:
            continue

        mnemonic_match = re.match(r'^(\w+(?:\.\w)?)', upper)
        if not mnemonic_match:
            continue

        total_instr += 1
        mnemonic = mnemonic_match.group(1)

        is_write = False
        write_size = 2
        if '.B' in mnemonic:
            write_size = 1

        if any(m in mnemonic for m in ['MOV', 'ADD', 'SUB', 'AND', 'BIS', 'BIC', 'XOR']):
            parts = upper.split(',')
            if len(parts) >= 2:
                dst = parts[-1].strip()
                if re.search(r'[&@]|[0-9]+\(R', dst):
                    is_write = True

        if is_write:
            write_points.append(total_instr)
            write_sizes.append(write_size)

    return total_instr, write_points, write_sizes


def analyze_live_state(asm_file, total_instr, write_points, write_sizes):
    """Estimate live state size at different execution progress percentages."""
    progress_points = [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0]
    results = {}

    for prog in progress_points:
        target_instr = int(total_instr * prog)
        cumulative_writes = 0
        unique_addrs = set()

        for idx, instr_num in enumerate(write_points):
            if instr_num <= target_instr:
                cumulative_writes += write_sizes[idx]
            else:
                break

        results[int(prog * 100)] = cumulative_writes

    return results


def main():
    print("=" * 80)
    print("Analysis 1: Consecutive Register-Only Instruction Sequences")
    print("=" * 80)

    all_reg_stats = {}
    for bench, asm_path in BENCHMARKS.items():
        full_path = os.path.join(ASAP_BASE, asm_path)
        with open(full_path) as f:
            lines = f.readlines()

        counter, seq_lengths = analyze_reg_only_sequences(lines)
        all_reg_stats[bench] = counter

        total_seqs = len(seq_lengths)
        avg_len = sum(seq_lengths) / max(1, total_seqs)
        max_len = max(seq_lengths) if seq_lengths else 0

        print(f"\n{bench}: {total_seqs} sequences, avg length={avg_len:.1f}, max={max_len}")
        print(f"  Length distribution:")
        for length in sorted(counter.keys()):
            count = counter[length]
            pct = count / total_seqs * 100
            bar = '█' * int(pct / 2)
            print(f"    {length:3d}: {count:4d} ({pct:5.1f}%) {bar}")

    print(f"\n\n{'=' * 80}")
    print("Analysis 2: Theoretical Restore Volume at Different Execution Progress")
    print("=" * 80)

    all_live_stats = {}
    for bench, asm_path in BENCHMARKS.items():
        full_path = os.path.join(ASAP_BASE, asm_path)
        with open(full_path) as f:
            lines = f.readlines()

        total_instr, write_points, write_sizes = count_memory_writes(lines)
        live_state = analyze_live_state(full_path, total_instr, write_points, write_sizes)
        all_live_stats[bench] = live_state

        print(f"\n{bench}: {total_instr} total instructions, {len(write_points)} memory writes")
        print(f"  Progress  Cumulative Memory Writes (bytes)")
        for pct, vol in sorted(live_state.items()):
            bar = '█' * (vol // 50)
            print(f"    {pct:3d}%:    {vol:6d}B  {bar}")

    # Export
    import csv
    with open("benchmark_stats.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "analysis", "key", "value"])
        for bench, counter in all_reg_stats.items():
            for length, count in sorted(counter.items()):
                w.writerow([bench, "reg_only_seq", f"length_{length}", count])
        for bench, live in all_live_stats.items():
            for pct, vol in sorted(live.items()):
                w.writerow([bench, "live_state", f"progress_{pct}pct", vol])
    print(f"\nCSV exported to benchmark_stats.csv")

    # Plot: Distribution of Consecutive Register-Only Instruction Sequences
    import os as _os
    _os.environ['MPLCONFIGDIR'] = '/tmp/mpl_config'
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    display_names = {
        'ar': 'AR', 'bc': 'BC', 'cf': 'Cuckoo', 'conv': 'Conv',
        'crc': 'CRC-16', 'adpcm_de': 'ADPCM-De', 'adpcm_en': 'ADPCM-En'
    }
    markers = ['o', 's', '^', 'D', 'v', 'h', 'p']

    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, (bench, counter) in enumerate(all_reg_stats.items()):
        total = sum(counter.values())
        if total == 0:
            continue
        lengths = sorted(counter.keys())
        cumulative = []
        running = 0
        for l in lengths:
            running += counter[l] / total * 100
            cumulative.append(running)
        ax.plot(lengths, cumulative, marker=markers[idx % len(markers)], markersize=8,
                linewidth=1.5, label=display_names.get(bench, bench))

    ax.set_xlabel('Consecutive Register-Only Instruction Sequence Length', fontsize=12)
    ax.set_ylabel('CDF (%)', fontsize=12)
    ax.set_title('CDF of Consecutive Register-Only Instruction Sequence Length', fontsize=14)
    ax.axhline(y=90, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    ax.legend(ncol=2, fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0.5)
    ax.set_ylim(bottom=0)

    out_path = '/Users/wyf/Desktop/实验图/reg_only_seq_distribution.png'
    plt.tight_layout()
    plt.savefig(out_path, dpi=200, bbox_inches='tight', facecolor='white')
    print(f"Plot saved to {out_path}")


if __name__ == "__main__":
    main()
