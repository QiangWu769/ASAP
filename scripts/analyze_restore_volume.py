#!/usr/bin/env python3
"""
ASAP Restore Data Volume Analysis

For each benchmark, calculates the restore data volume at different
power failure counts (0-100), with 20 random trials per failure count.

Restore mechanism (from stage11 + stage11b):
1. Scalar restore: read WID → lookup restore table → copy FRAM slots → SRAM (4B/entry)
2. Array restore (stage11b):
   - WID < array_write_start: skip (0B)
   - WID in write range: incremental restore (index × element_size bytes)
   - WID > array_write_end: full restore (total_bytes)
"""
import json
import random
import csv
import os

ASAP_BASE = "/Users/wyf/Desktop/code/ASAP_right_副本/backups/conv成功版本"

BENCHMARKS = {
    "ar":        {"build_dir": "build_ar_restore",        "loop_count": {"total_wid_execs": 10000}},
    "bc":        {"build_dir": "build_bc_restore",        "loop_count": {"total_wid_execs": 8000}},
    "cf":        {"build_dir": "build_cf_restore",        "loop_count": {"total_wid_execs": 6000}},
    "conv":      {"build_dir": "build",                   "loop_count": {"total_wid_execs": 8700}},
    "crc":       {"build_dir": "build_crc_restore",       "loop_count": {"total_wid_execs": 3000}},
    "adpcm_de":  {"build_dir": "build_adpcm_restore",     "loop_count": {"total_wid_execs": 2500}},
    "adpcm_en":  {"build_dir": "build_adpcm_encode_restore", "loop_count": {"total_wid_execs": 3000}},
}

N_TRIALS = 20
FAILURE_COUNTS = list(range(0, 101))


def load_benchmark_data(bench_name, build_dir):
    bdir = os.path.join(ASAP_BASE, build_dir)

    with open(os.path.join(bdir, "pc_ranges.json")) as f:
        pc_ranges = json.load(f)

    with open(os.path.join(bdir, "fram_slots.json")) as f:
        fram_slots = json.load(f)

    try:
        with open(os.path.join(bdir, "loop_arrays.json")) as f:
            loop_arrays = json.load(f)
    except FileNotFoundError:
        loop_arrays = {"arrays": {}, "writes": {}}

    try:
        with open(os.path.join(bdir, "candidates.json")) as f:
            candidates = json.load(f)
    except FileNotFoundError:
        candidates = {}

    return pc_ranges, fram_slots, loop_arrays, candidates


def compute_restore_volume(wid_idx, pc_ranges, fram_slots, loop_arrays, candidates, total_wid_execs):
    """Compute restore data volume for a power failure at a given WID execution index."""
    ranges = pc_ranges.get("ranges", [])
    array_mirrors = fram_slots.get("array_mirrors", {})
    array_writes = loop_arrays.get("writes", {})
    arrays_info = loop_arrays.get("arrays", {})

    if not ranges:
        return 0

    n_wids = len(ranges)
    wid_data = ranges[wid_idx % n_wids]
    wid_name = wid_data["wid"]
    wid_num = int(wid_name[1:])

    # 1. Scalar restore: restore_list entries × 4B (2B read FRAM + 2B write SRAM)
    restore_list = wid_data.get("restore_list", [])
    scalar_restore = len(restore_list) * 4

    # 2. Array restore (incremental logic from stage11b)
    array_restore = 0
    for array_name, mirror_config in array_mirrors.items():
        total_bytes = mirror_config.get("total_bytes", 0)
        array_size = mirror_config.get("size", 0)
        element_size = mirror_config.get("element_size", 2)

        wid_list = []
        for w, info in array_writes.items():
            if info.get("array_name") == array_name:
                wid_list.append(int(w[1:]))

        if not wid_list:
            continue

        min_wid = min(wid_list)
        max_wid = max(wid_list)

        if wid_num < min_wid:
            pass
        elif wid_num > max_wid:
            array_restore += total_bytes
        else:
            progress = (wid_num - min_wid) / max(1, max_wid - min_wid)
            restored_elements = max(1, int(progress * array_size))
            array_restore += restored_elements * element_size

    # 3. SP + PC restore overhead
    sp_pc_restore = 4  # 2B SP + 2B PC

    return scalar_restore + array_restore + sp_pc_restore


def analyze_benchmark(bench_name, config):
    build_dir = config["build_dir"]
    total_execs = config["loop_count"]["total_wid_execs"]

    try:
        pc_ranges, fram_slots, loop_arrays, candidates = load_benchmark_data(bench_name, build_dir)
    except Exception as e:
        print(f"  Error loading {bench_name}: {e}")
        return None

    ranges = pc_ranges.get("ranges", [])
    n_wids = len(ranges)

    results = {}
    for nf in FAILURE_COUNTS:
        trials = []
        for t in range(N_TRIALS):
            rng = random.Random(42 + t + nf * 1000)
            total_restore = 0
            for _ in range(nf):
                fail_pos = rng.randint(0, n_wids - 1)
                vol = compute_restore_volume(fail_pos, pc_ranges, fram_slots, loop_arrays, candidates, total_execs)
                total_restore += vol
            trials.append(total_restore)
        results[nf] = trials

    return results


def main():
    all_results = {}

    for bench_name, config in BENCHMARKS.items():
        print(f"Analyzing {bench_name}...")
        results = analyze_benchmark(bench_name, config)
        if results:
            all_results[bench_name] = results

    # Print summary
    for bench_name, results in all_results.items():
        print(f"\n{'='*120}")
        print(f"Benchmark: {bench_name}")
        print(f"{'='*120}")
        h = f"  {'N':>3}"
        for t in range(1, N_TRIALS + 1):
            h += f" {'T'+str(t):>6}"
        h += f" {'AVG':>8}"
        print(h)
        print(f"  {'-' * (len(h)-2)}")
        for nf in [0, 1, 2, 3, 5, 10, 20, 50, 100]:
            if nf in results:
                vs = results[nf]
                avg = sum(vs) / len(vs)
                r = f"  {nf:>3}"
                for v in vs:
                    r += f" {v:>6}"
                r += f" {avg:>8.1f}"
                print(r)

    # Export CSV
    fn = os.path.join(ASAP_BASE, "restore_estimation.csv")
    with open(fn, "w", newline="") as f:
        w = csv.writer(f)
        header = ["benchmark", "n_failures"]
        header += [f"trial_{i+1}" for i in range(N_TRIALS)]
        header += ["average"]
        w.writerow(header)
        for bench_name, results in all_results.items():
            for nf in FAILURE_COUNTS:
                vs = results[nf]
                avg = round(sum(vs) / len(vs), 1)
                w.writerow([bench_name, nf] + vs + [avg])
    print(f"\nCSV exported to {fn}")

    # Summary table
    print(f"\n{'='*80}")
    print("SUMMARY: Restore volume per failure count (average of 20 trials)")
    print(f"{'-'*80}")
    h = f"{'Benchmark':<12}"
    for nf in [0, 1, 5, 10, 20, 50, 100]:
        h += f" {'N='+str(nf):>8}"
    print(h)
    print(f"{'-'*80}")
    for bench_name, results in all_results.items():
        r = f"{bench_name:<12}"
        for nf in [0, 1, 5, 10, 20, 50, 100]:
            avg = sum(results[nf]) / len(results[nf])
            r += f" {avg:>8.0f}"
        print(r)


if __name__ == "__main__":
    main()
