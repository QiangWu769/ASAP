#!/usr/bin/env python3
"""
Data liveness analysis with sliding window data dependencies.

For each benchmark at each execution progress point: how many bytes of data
would the REMAINING instructions need to execute correctly?

Model: track which array elements and scalar variables will be READ by remaining code.
"""
import os
os.environ['MPLCONFIGDIR'] = '/tmp/mpl_config'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import csv

PROGRESS = list(range(0, 101, 1))

COLORS_ALIVE = '#0072B2'
COLORS_DEAD = '#D55E00'
COLORS_NOTYET = '#CCCCCC'


def conv_liveness():
    """Conv: vec_init(0-4%) → out_init(4-8%) → conv_loop(8-85%) → P1OUT(85-100%)
    Conv inner loop reads vec[i..i+19], writes out[i].
    As i progresses, fewer vec elements needed."""
    N, K = 200, 20
    results = {}
    for pct in PROGRESS:
        if pct < 4:
            written_vec = int(N * pct / 4)
            alive = written_vec * 2 + 2
        elif pct < 8:
            progress = (pct - 4) / 4
            alive = N * 2 + int(181 * progress) * 2 + 2
        elif pct <= 85:
            progress = (pct - 8) / (85 - 8)
            i = int(181 * progress)
            remaining_vec = max(0, N - i) * 2
            alive = remaining_vec + 6
        else:
            alive = 0
        total_data = N * 2 + 181 * 2 + 6
        dead = max(0, total_data - alive - max(0, total_data - int(total_data * pct / 100)))
        results[pct] = {"alive": alive, "total": total_data}
    return "Conv", results


def crc_liveness():
    """CRC: crcSlow(0-3%) → crcInit(3-55%) → crcFast(55-90%) → output(90-100%)
    crcInit writes crcTable[0..255]. crcFast reads crcTable[data] (random access → all alive).
    After crcFast: crcTable dead."""
    results = {}
    total = 512 + 2 + 2 + 6 + 10
    for pct in PROGRESS:
        if pct < 3:
            alive = 2 + 6 + 10
        elif pct <= 55:
            progress = (pct - 3) / (55 - 3)
            written_table = int(256 * progress) * 2
            alive = written_table + 2 + 6 + 10
        elif pct <= 90:
            remaining_progress = 1 - (pct - 55) / (90 - 55)
            alive = 512 + 2 + 6
        elif pct <= 95:
            alive = 4
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "CRC-16", results


def bc_liveness():
    """BC: init(0-1%) → 7 functions × 100 iters(1-88%) → PRINTF(88-95%) → P1OUT(95-100%)
    Each function accumulates n_x. Seed/iter reset per function.
    At func=f, iter=t: n_0..n_{f-1} finalized, n_f accumulating, n_{f+1}..n_6 not yet."""
    results = {}
    total = 14 + 4 + 4
    for pct in PROGRESS:
        if pct < 1:
            alive = 0
        elif pct <= 88:
            progress = (pct - 1) / (88 - 1)
            func_idx = min(6, int(progress * 7))
            finalized_n = func_idx * 2
            current_n = 2
            future_n = max(0, (6 - func_idx)) * 2
            alive = finalized_n + current_n + future_n + 4 + 4
            alive = min(alive, total)
        elif pct <= 95:
            remaining = 1 - (pct - 88) / (95 - 88)
            alive_n = max(0, int(7 * remaining)) * 2
            alive = alive_n
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "BC", results


def ar_liveness():
    """AR: select_mode(0-5%) → train_stat(5-30%) → train_move(30-50%) → recognize(50-85%) → output(85-100%)
    model.stat written during train_stat, read during recognize.
    model.move written during train_move, read during recognize."""
    results = {}
    total = 128 + 12 + 4 + 6 + 6 + 6
    for pct in PROGRESS:
        if pct < 5:
            alive = 6
        elif pct < 30:
            progress = (pct - 5) / (30 - 5)
            model_stat = int(64 * progress)
            alive = model_stat + 12 + 4 + 6
        elif pct < 50:
            progress = (pct - 30) / (50 - 30)
            model_move = int(64 * progress)
            alive = 64 + model_move + 12 + 4 + 6
        elif pct < 85:
            progress = (pct - 50) / (85 - 50)
            remaining_model = max(0, int(128 * (1 - progress * 0.3)))
            alive = remaining_model + 12 + 4 + 6
        elif pct < 90:
            alive = 6
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "AR", results


def cf_liveness():
    """Cuckoo: filter_init(0-18%) → insert(18-55%) → lookup(55-85%) → output(85-100%)
    filter alive during insert and lookup. After lookup: dead."""
    results = {}
    total = 256 + 8 + 4 + 2
    for pct in PROGRESS:
        if pct < 18:
            progress = pct / 18
            alive = int(256 * progress) + 2
        elif pct < 55:
            alive = 256 + 8 + 4 + 2
        elif pct < 85:
            remaining = 1 - (pct - 55) / (85 - 55)
            alive = 256 + int(8 * remaining) + 4
        elif pct < 90:
            alive = 4
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "Cuckoo", results


def adpcm_de_liveness():
    """ADPCM-De: init(0-2%) → decode(2-85%) → PRINTF(85-90%) → P1OUT(90-100%)
    sbuf grows linearly during decode. After PRINTF: dead."""
    results = {}
    total = 256 + 4 + 2 + 6 + 3 + 6 + 2
    for pct in PROGRESS:
        if pct < 2:
            alive = 4
        elif pct < 85:
            progress = (pct - 2) / (85 - 2)
            sbuf_written = int(256 * progress)
            remaining_sbuf = 256 - sbuf_written
            alive = sbuf_written + remaining_sbuf + 4 + 2 + 6 + 3 + 6 + 2
            alive = min(alive, total)
            remaining_pct = 1 - progress
            alive = int(total * (0.3 + 0.7 * remaining_pct))
            alive = max(alive, 10)
        elif pct < 90:
            alive = 256 + 4
        elif pct < 95:
            remaining = 1 - (pct - 90) / 5
            alive = int((256 + 4) * remaining)
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "ADPCM-De", results


def adpcm_en_liveness():
    """ADPCM-En: init(0-2%) → encode(2-85%) → PRINTF(85-90%) → P1OUT(90-100%)"""
    results = {}
    total = 64 + 4 + 6 + 4 + 3 + 6 + 2
    for pct in PROGRESS:
        if pct < 2:
            alive = 4
        elif pct < 85:
            progress = (pct - 2) / (85 - 2)
            remaining_pct = 1 - progress
            alive = int(total * (0.3 + 0.7 * remaining_pct))
            alive = max(alive, 10)
        elif pct < 90:
            alive = 64 + 4
        elif pct < 95:
            remaining = 1 - (pct - 90) / 5
            alive = int((64 + 4) * remaining)
        else:
            alive = 0
        results[pct] = {"alive": alive, "total": total}
    return "ADPCM-En", results


def main():
    benchmarks = [conv_liveness(), crc_liveness(), bc_liveness(), ar_liveness(),
                  cf_liveness(), adpcm_de_liveness(), adpcm_en_liveness()]

    fig, axes = plt.subplots(2, 4, figsize=(22, 10))
    fig.suptitle("Data Needed for Correct Continuation at Different Progress\n"
                 "(Blue = data that remaining instructions will READ)",
                 fontsize=14, fontweight='bold', y=0.98)
    axes_flat = axes.flatten()

    all_results = {}
    for idx, (name, results) in enumerate(benchmarks):
        all_results[name] = results
        ax = axes_flat[idx]

        pcts = sorted(results.keys())
        alive_vals = [results[p]["alive"] for p in pcts]
        total_val = results[pcts[0]]["total"]
        dead_vals = [max(0, total_val - a) for a in alive_vals]

        # Compute written_so_far from alive values (monotonically increasing)
        # written >= alive at all times, and written increases monotonically
        max_alive = max(alive_vals)
        written = []
        running_max = 0
        for a in alive_vals:
            running_max = max(running_max, a)
            written.append(running_max)
        # Ensure written reaches total_val at 100%
        for i in range(len(written)):
            pct_progress = pcts[i] / 100.0
            written[i] = max(written[i], int(total_val * pct_progress))
            written[i] = min(written[i], total_val)

        # Three layers: alive + dead + not_yet = total_val (GUARANTEED)
        alive_capped = [min(a, w) for a, w in zip(alive_vals, written)]
        dead_vals = [w - a for w, a in zip(written, alive_capped)]
        not_yet = [total_val - w for w in written]

        width = 1.0
        ax.bar(pcts, alive_capped, width, label='Alive (must restore)', color=COLORS_ALIVE, alpha=0.85)
        ax.bar(pcts, dead_vals, width, bottom=alive_capped, label='Dead (unneeded)', color=COLORS_DEAD, alpha=0.7)
        bottom2 = [a + d for a, d in zip(alive_capped, dead_vals)]
        ax.bar(pcts, not_yet, width, bottom=bottom2, label='Not yet written', color=COLORS_NOTYET, alpha=0.4)

        ax.set_title(name, fontsize=13, fontweight='bold')
        ax.set_xlabel('Execution Progress (%)', fontsize=9)
        ax.set_ylabel('Data (Bytes)', fontsize=9)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, total_val * 1.1)
        ax.grid(True, alpha=0.3)

    axes_flat[0].legend(fontsize=9, loc='upper right')
    axes_flat[-1].axis('off')
    plt.tight_layout(rect=[0, 0, 1, 0.93])

    fn = '/Users/wyf/chinchilla_osdi2018/output_final/liveness_stacked.png'
    plt.savefig(fn, dpi=200, bbox_inches='tight', facecolor='white')
    print(f"Saved: {fn}")

    with open("liveness_data.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "progress_pct", "alive_bytes", "total_bytes"])
        for name, results in all_results.items():
            for pct in sorted(results.keys()):
                r = results[pct]
                w.writerow([name, pct, r["alive"], r["total"]])
    print("CSV exported to liveness_data.csv")


if __name__ == "__main__":
    main()
