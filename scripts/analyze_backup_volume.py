#!/usr/bin/env python3
"""
ASAP Backup Data Volume Analysis
Estimates total FRAM backup bytes for 7 benchmarks under different power failure counts.
"""

import json
import re
import random
import os
import sys

def parse_wid_backup_bytes(asm_file):
    """Parse instrumented assembly to count FRAM backup bytes per WID."""
    with open(asm_file, 'r') as f:
        lines = f.readlines()

    wid_info = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        wid_label_m = re.match(r'^__WID_(W\d+):', line)
        if wid_label_m:
            wid_id = wid_label_m.group(1)
            fram_bytes = 0

            # Scan backward from this label to find all FRAM writes belonging to this WID
            j = i - 1
            while j >= 0:
                prev = lines[j].strip()
                prev_upper = prev.upper()

                if prev.startswith('.global __WID_'):
                    j -= 1
                    continue

                if prev.startswith(';') or not prev:
                    if 'ASAP' in prev and '备份' in prev:
                        break  # reached the backup comment, stop
                    if '===' in prev and 'ASAP' in prev:
                        break
                    j -= 1
                    continue

                # FRAM writes: MOV to &SYMBOL where SYMBOL is backup-related
                if re.search(r'&__SLOT_', prev, re.IGNORECASE):
                    if 'MOV.B' in prev_upper:
                        fram_bytes += 1
                    else:
                        fram_bytes += 2
                elif re.search(r'&ASAP_SP_SAVE', prev, re.IGNORECASE) and 'MOV' in prev_upper:
                    fram_bytes += 2
                elif re.search(r'&__ADDR_SLOT_', prev, re.IGNORECASE) and 'MOV' in prev_upper:
                    fram_bytes += 2
                elif re.search(r'MOV\.\w\s+@R\d+,\s*@R\d+', prev_upper):
                    # Array mirror write - check if previous lines computed FRAM address
                    for k in range(max(0, j-5), j):
                        if '__backup_' in lines[k].lower() or '__mirror_' in lines[k].lower():
                            fram_bytes += 2
                            break

                # Stop if we hit another WID label or its save instruction
                if re.match(r'^__WID_W\d+:', prev):
                    break
                if '&ASAP_WID_SAVE' in prev and 'MOV' in prev_upper:
                    break
                j -= 1

            # Also scan forward for the WID save instruction
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip().upper()
                if 'ASAP_WID_SAVE' in next_line and 'MOV' in next_line:
                    fram_bytes += 2

            wid_info[wid_id] = fram_bytes
        i += 1

    return wid_info


def get_benchmark_execution_model(benchmark, candidates_file):
    """
    Return execution model: list of (wid_id, exec_count) for one complete iteration.
    """
    with open(candidates_file, 'r') as f:
        candidates = json.load(f)

    wid_list = sorted(candidates.keys(), key=lambda x: int(x[1:]))

    models = {
        'conv': get_conv_model,
        'ar': get_ar_model,
        'bc': get_bc_model,
        'cf': get_cf_model,
        'crc': get_crc_model,
        'adpcm_de': get_adpcm_de_model,
        'adpcm_en': get_adpcm_en_model,
    }

    if benchmark in models:
        return models[benchmark](wid_list, candidates)
    else:
        return [(w, 1) for w in wid_list]


def get_conv_model(wid_list, candidates):
    """
    Conv: N=200, K=20, out_size=N-K+1=181
    Loop structure:
      W001: i=0 for vec init → 1
      W002: vec[i]=i (array) → 200
      W003: i++ → 200
      W004: i=0 for out init → 1
      W005: out[i]=0 (array) → 181
      W006: i++ → 181
      W007: i=0 for conv outer → 1
      W008: temp=0 → 181
      W009: j=0 → 181
      W010: temp+=vec[i+j] → 181*20=3620
      W011: j++ → 181*20=3620
      W012: out[i]=temp (array) → 181
      W013: i++ → 181
    """
    return [
        ('W001', 1), ('W002', 200), ('W003', 200),
        ('W004', 1), ('W005', 181), ('W006', 181),
        ('W007', 1), ('W008', 181), ('W009', 181),
        ('W010', 3620), ('W011', 3620),
        ('W012', 181), ('W013', 181),
    ]


def get_ar_model(wid_list, candidates):
    """
    AR: Activity Recognition
    Main flow in one complete iteration:
      1. select_mode (count=1) → MODE_TRAIN_STATIONARY → train(model.stationary)
      2. select_mode (count=2) → MODE_TRAIN_MOVING → train(model.moving)
      3. select_mode (count=3) → MODE_RECOGNIZE → recognize(&model)
      4. select_mode (count=4) → complete

    train() is called 2 times:
      warmup_sensor: 3 iterations of accel_sample
      for(i=0;i<16;i++): acquire_window(3 samples) + transform(3) + featurize

    recognize() is called 1 time:
      for(i=0;i<8;i++): acquire_window(3) + transform(3) + featurize + classify(16 iters) + record_stats

    Need to count WIDs by analyzing the actual instrumented assembly.
    Since AR has many WIDs across multiple functions, use a detailed model.
    """
    # AR typically has 70-90+ WIDs. I need to analyze the actual WID distribution.
    # For now, build a simplified model based on function call structure.

    # Let me count WIDs per function from candidates
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    # Execution count per function call during one complete AR iteration:
    # warmup_sensor: called 2 times (once per train)
    #   - internally loops 3 times
    # accel_sample: called by warmup(2*3=6) + acquire_window(2*16*3 + 1*8*3 = 96+24=120) = 126 times
    # acquire_window: called 2*16 + 1*8 = 40 times, each has 3 iterations
    # transform: called 2*16 + 1*8 = 40 times, each iterates 3 times
    # featurize: called 2*16 + 1*8 = 40 times, each iterates 3 times (2 passes)
    # classify: called 1*8 = 8 times, each iterates 16 times
    # record_stats: called 1*8 = 8 times
    # select_mode: called 4 times
    # train: called 2 times, each has 16 iterations
    # recognize: called 1 time, has 8 iterations
    # main: called 1 time
    # sqrt16: called inside featurize, 2 calls per featurize = 80 calls

    func_exec_counts = {
        'main': 1,
        'init': 1,
        'select_mode': 4,
        'warmup_sensor': 2,
        'accel_sample': 126,  # 2*3 + 2*16*3 + 8*3 = 6+96+24=126
        'acquire_window': 40,  # 2*16 + 8 = 40
        'transform': 40,
        'featurize': 40,
        'classify': 8,
        'record_stats': 8,
        'print_stats': 1,
        'train': 2,
        'recognize': 1,
        'sqrt16': 80,  # 2 per featurize call, 40 featurize calls
    }

    # For WIDs in loops within a function, multiply by inner loop count
    # Each function's internal loop structure:
    inner_loop_counts = {
        'warmup_sensor': 3,  # while(discardedSamplesCount++ < 3)
        'acquire_window': 3,  # while(samplesInWindow < 3)
        'transform': 3,  # for(i=0;i<3;i++)
        'featurize': 3,  # for(i=0;i<3;i++) - two separate loops
        'classify': 16,  # for(i=0;i<16;i++)
        'train': 16,  # for(i=0;i<16;i++)
        'recognize': 8,  # for(i=0;i<8;i++)
        'sqrt16': 15,  # while loop, approximately 15 iterations for 16-bit
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)

        # Determine if this WID is inside a loop within the function
        # Heuristic: WIDs that write to loop counter variables are executed
        # once per loop iteration
        inner_count = 1
        if func in inner_loop_counts:
            inner_count = inner_loop_counts[func]

        # For WIDs in main that are loop init (executed once per function call),
        # don't multiply by inner loop count
        # This is a simplification - some WIDs are before the loop, some inside
        # For accuracy, mark WIDs that are loop counters vs loop body
        exec_count = base_count * inner_count

        result.append((wid, exec_count))

    return result


def get_bc_model(wid_list, candidates):
    """
    BC: Bit Count
    Main loop: for(i=0; i<ITER; i++) (ITER=100)
      Calls: bit_count, bitcount, ntbl_bitcount, btbl_bitcount,
             ar_bitcount, ntbl_bitcnt, BW_btbl_bitcount
    Each function is called 100 times per outer loop iteration.
    Internal loops:
      - bit_count: do-while loop, avg ~16 iterations for 32-bit
      - ntbl_bitcount: no loop (just table lookups)
      - btbl_bitcount: no loop
      - ar_bitcount: for loop 4 iterations
      - ntbl_bitcnt: no loop
      - BW_btbl_bitcount: no loop
      - bitcount: no loop (just arithmetic)
    """
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    func_exec_counts = {
        'main': 1,
        'init': 1,
        'bit_count': 100,
        'bitcount': 100,
        'ntbl_bitcount': 100,
        'btbl_bitcount': 100,
        'ar_bitcount': 100,
        'ntbl_bitcnt': 100,
        'BW_btbl_bitcount': 100,
    }

    inner_loop_counts = {
        'bit_count': 16,  # do-while, avg iterations
        'ar_bitcount': 4,  # for loop with 4 iterations (sizeof(int))
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)
        inner_count = inner_loop_counts.get(func, 1)
        exec_count = base_count * inner_count
        result.append((wid, exec_count))

    return result


def get_cf_model(wid_list, candidates):
    """
    CF: Cuckoo Filter
    - filter init: for(i=0; i<128; i++) filter[i]=0 → 128
    - insert phase: for(i=0; i<32; i++) insert(key) → 32 calls
      - insert has up to 8 relocations (do-while)
    - lookup phase: for(i=0; i<32; i++) lookup(key) → 32 calls
    """
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    # cf_rand: called inside insert, typically once per insert
    # djb_hash: called by hash_to_fingerprint, hash_key_to_index, hash_fp_to_index
    func_exec_counts = {
        'main': 1,
        'init': 1,
        'insert': 32,
        'lookup': 32,
        'cf_rand': 32,
        'djb_hash': 32 * 3 + 32 * 3 + 32 * 4,  # insert(3 hashes) + lookup(3 hashes) + relocations
        'hash_to_fingerprint': 32 + 32,  # insert + lookup
        'hash_key_to_index': 32 + 32,
        'hash_fp_to_index': 32 + 32 * 4,  # insert + relocation hashes
        'generate_key': 32 + 32,  # insert phase + lookup phase
    }

    inner_loop_counts = {
        'djb_hash': 2,  # for(i=0; i<len; data++, i++) where len=2 typically
        'insert': 4,  # do-while max 8 relocations, avg ~4
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)
        inner_count = inner_loop_counts.get(func, 1)
        exec_count = base_count * inner_count
        result.append((wid, exec_count))

    return result


def get_crc_model(wid_list, candidates):
    """
    CRC: CRC-CCITT (16-bit)
    - crcSlow: for(byte=0; byte<9; byte++) for(bit=8; bit>0; bit--) → 72 iterations
    - crcInit: for(dividend=0; dividend<256; dividend++) for(bit=8; bit>0; bit--) → 2048
      + crcTable[dividend] = remainder → 256 writes
    - crcFast: for(byte=0; byte<9; byte++) → 9 iterations
    """
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    func_exec_counts = {
        'main': 1,
        'init': 1,
        'crcSlow': 1,
        'crcInit': 1,
        'crcFast': 1,
        'reflect': 0,  # REFLECT_DATA is FALSE, so reflect is not called
    }

    inner_loop_counts = {
        'crcSlow': 72,  # 9 bytes * 8 bits
        'crcInit': 256,  # 256 dividends, each with 8 bit iterations + 1 table write
        'crcFast': 9,   # 9 bytes
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)
        inner_count = inner_loop_counts.get(func, 1)
        exec_count = base_count * inner_count
        result.append((wid, exec_count))

    return result


def get_adpcm_de_model(wid_list, candidates):
    """
    ADPCM Decode:
    Main: for each sample (NUM_SAMPLES, typically 100 samples)
      - adpcm_decoder processes 4-bit codes
    """
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    func_exec_counts = {
        'main': 1,
        'init': 1,
        'adpcm_decoder': 1,  # called once, but has internal loop
    }

    inner_loop_counts = {
        'adpcm_decoder': 100,  # processes ~100 samples
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)
        inner_count = inner_loop_counts.get(func, 1)
        exec_count = base_count * inner_count
        result.append((wid, exec_count))

    return result


def get_adpcm_en_model(wid_list, candidates):
    """
    ADPCM Encode: similar to decode
    """
    func_wids = {}
    for wid, info in candidates.items():
        func = info.get('function', 'unknown')
        if func not in func_wids:
            func_wids[func] = []
        func_wids[func].append(wid)

    func_exec_counts = {
        'main': 1,
        'init': 1,
        'adpcm_coder': 1,
    }

    inner_loop_counts = {
        'adpcm_coder': 100,
    }

    result = []
    for wid in sorted(wid_list, key=lambda x: int(x[1:])):
        info = candidates[wid]
        func = info.get('function', 'unknown')
        base_count = func_exec_counts.get(func, 1)
        inner_count = inner_loop_counts.get(func, 1)
        exec_count = base_count * inner_count
        result.append((wid, exec_count))

    return result


def build_execution_trace(wid_backup_bytes, exec_model):
    """
    Build the execution trace as a flat list of (wid_id, backup_bytes) events.
    Each WID execution is one event. WIDs in loops produce multiple events.
    """
    trace = []
    for wid_id, exec_count in exec_model:
        bytes_per = wid_backup_bytes.get(wid_id, 4)
        for _ in range(exec_count):
            trace.append((wid_id, bytes_per))
    return trace


def compute_optimized_bytes(wid_backup_bytes, asm_file):
    """
    Compute optimized backup bytes per WID (Block-Level SR & PC optimization).
    Only removes WID_SAVE (2 bytes per WID). Keeps SP_SAVE and everything else.
    The WID/PC info is encoded in SR instead of explicit WID_SAVE write.
    """
    optimized = {}
    for wid_id, current_bytes in wid_backup_bytes.items():
        optimized[wid_id] = max(0, current_bytes - 2)  # remove 2 bytes for WID_SAVE
    return optimized


def simulate_failures(trace, num_failures, num_trials=20, seed_base=42):
    """
    Simulate power failures and compute total backup data.

    Model:
    - Execution is a sequence of M WID events
    - Each event writes backup_bytes to FRAM
    - Power failure at a random position (uniformly distributed)
    - After recovery, execution continues from the last WID before failure

    For each failure:
    - If failure is between event[k] and event[k+1]:
      overhead = 2 bytes (WID re-save at recovery point)
    - If failure is during event[k]'s backup sequence:
      overhead ≈ backup_bytes[k] (re-execution of partial backup)
      Probability: proportional to backup_bytes[k] / total_instructions_between_wids

    Simplified model: assume each WID backup takes ~3 instructions,
    and there are ~20 non-WID instructions between WIDs.
    So probability of failing during backup = 3/(3+20) ≈ 13%
    """
    M = len(trace)
    if M == 0:
        return [0] * num_trials

    base_backup = sum(b for _, b in trace)

    # Average instructions between WIDs (non-backup code)
    AVG_INTER_WID_INSTRUCTIONS = 15

    results = []
    for trial in range(num_trials):
        rng = random.Random(seed_base + trial * 1000 + num_failures * 100)
        total_overhead = 0

        # For each failure, compute overhead
        remaining_trace_len = M
        for _ in range(num_failures):
            if remaining_trace_len <= 0:
                break

            # Random failure position (which WID interval)
            fail_pos = rng.randint(0, remaining_trace_len - 1)

            _, wid_bytes = trace[fail_pos % M]

            # Decide if failure is during WID backup or between WIDs
            backup_instr = max(1, wid_bytes // 2)  # ~1 instruction per 2 bytes
            total_instr = backup_instr + AVG_INTER_WID_INSTRUCTIONS

            if rng.random() < backup_instr / total_instr:
                # Failure during backup: overhead = full re-backup
                total_overhead += wid_bytes
            else:
                # Failure between WIDs: overhead = WID re-save only
                total_overhead += 2

        total = base_backup + total_overhead
        results.append(total)

    return results


def analyze_benchmark(benchmark, build_dir):
    """Analyze a single benchmark."""
    asm_file = os.path.join(build_dir, 'A_redirected.s')
    candidates_file = os.path.join(build_dir, 'candidates.json')

    if not os.path.exists(asm_file) or not os.path.exists(candidates_file):
        print(f"  [ERROR] Missing files for {benchmark}")
        return None

    wid_backup_bytes = parse_wid_backup_bytes(asm_file)
    exec_model = get_benchmark_execution_model(benchmark, candidates_file)

    # Version A: with inner loops
    trace_with_loops = build_execution_trace(wid_backup_bytes, exec_model)

    # Version B: without inner loops (each WID counted once)
    exec_model_no_loops = [(wid, 1) for wid, _ in exec_model]
    trace_no_loops = build_execution_trace(wid_backup_bytes, exec_model_no_loops)

    # Optimized version: value-only backup
    optimized_bytes = compute_optimized_bytes(wid_backup_bytes, asm_file)
    trace_opt_with_loops = build_execution_trace(optimized_bytes, exec_model)
    trace_opt_no_loops = build_execution_trace(optimized_bytes, exec_model_no_loops)

    return {
        'wid_backup_bytes': wid_backup_bytes,
        'optimized_bytes': optimized_bytes,
        'exec_model': exec_model,
        'trace_with_loops': trace_with_loops,
        'trace_no_loops': trace_no_loops,
        'trace_opt_with_loops': trace_opt_with_loops,
        'trace_opt_no_loops': trace_opt_no_loops,
        'num_wids': len(wid_backup_bytes),
        'base_with_loops': sum(b for _, b in trace_with_loops),
        'base_no_loops': sum(b for _, b in trace_no_loops),
        'base_opt_with_loops': sum(b for _, b in trace_opt_with_loops),
        'base_opt_no_loops': sum(b for _, b in trace_opt_no_loops),
        'total_wid_execs_with_loops': len(trace_with_loops),
    }


def main():
    benchmarks = {
        'ar': 'build_ar_analysis',
        'bc': 'build_bc_analysis',
        'cf': 'build_cf_analysis',
        'conv': 'build_conv_analysis',
        'crc': 'build_crc_analysis',
        'adpcm_de': 'build_adpcm_de_analysis',
        'adpcm_en': 'build_adpcm_en_analysis',
    }

    failure_counts = [0, 1, 2, 3, 4, 5, 6, 7, 10]
    num_trials = 20

    all_results = {}

    print("=" * 80)
    print("ASAP Backup Data Volume Analysis")
    print("=" * 80)

    for bm_name, build_dir in benchmarks.items():
        print(f"\n{'=' * 60}")
        print(f"Benchmark: {bm_name}")
        print(f"{'=' * 60}")

        result = analyze_benchmark(bm_name, build_dir)
        if result is None:
            continue

        all_results[bm_name] = result

        print(f"  Unique WIDs: {result['num_wids']}")
        print(f"  WID backup bytes: {result['wid_backup_bytes']}")
        print(f"  Total WID executions (with loops): {result['total_wid_execs_with_loops']}")
        print(f"  --- Current (with WID+SP saves) ---")
        print(f"  Base backup (with loops): {result['base_with_loops']} bytes")
        print(f"  Base backup (no loops): {result['base_no_loops']} bytes")
        print(f"  --- Optimized (value-only, no WID/SP saves) ---")
        print(f"  Per-WID optimized bytes: {result['optimized_bytes']}")
        print(f"  Base backup (with loops): {result['base_opt_with_loops']} bytes")
        print(f"  Base backup (no loops): {result['base_opt_no_loops']} bytes")

    # Generate results table
    print("\n\n" + "=" * 120)
    print("RESULTS: Version A - With Inner Loops")
    print("=" * 120)

    for bm_name in benchmarks:
        if bm_name not in all_results:
            continue
        result = all_results[bm_name]
        trace = result['trace_with_loops']

        print(f"\n--- {bm_name} (base={result['base_with_loops']} bytes, "
              f"{result['total_wid_execs_with_loops']} WID executions) ---")
        print(f"{'Failures':>8} | {'Trial Results (bytes)':^80} | {'Average':>8}")
        print("-" * 105)

        for n_fail in failure_counts:
            trial_results = simulate_failures(trace, n_fail, num_trials)
            avg = sum(trial_results) / len(trial_results)
            trials_str = ', '.join(str(r) for r in trial_results)
            print(f"{n_fail:>8} | {trials_str:<80} | {avg:>8.1f}")

    print("\n\n" + "=" * 120)
    print("RESULTS: Version B - Without Inner Loops (each WID counted once)")
    print("=" * 120)

    for bm_name in benchmarks:
        if bm_name not in all_results:
            continue
        result = all_results[bm_name]
        trace = result['trace_no_loops']

        print(f"\n--- {bm_name} (base={result['base_no_loops']} bytes, "
              f"{result['num_wids']} WID executions) ---")
        print(f"{'Failures':>8} | {'Trial Results (bytes)':^80} | {'Average':>8}")
        print("-" * 105)

        for n_fail in failure_counts:
            trial_results = simulate_failures(trace, n_fail, num_trials)
            avg = sum(trial_results) / len(trial_results)
            trials_str = ', '.join(str(r) for r in trial_results)
            print(f"{n_fail:>8} | {trials_str:<80} | {avg:>8.1f}")

    # Optimized results
    print("\n\n" + "=" * 120)
    print("RESULTS: Version C - Optimized (Value-Only) With Inner Loops")
    print("=" * 120)

    for bm_name in benchmarks:
        if bm_name not in all_results:
            continue
        result = all_results[bm_name]
        trace = result['trace_opt_with_loops']

        print(f"\n--- {bm_name} (base={result['base_opt_with_loops']} bytes, "
              f"{result['total_wid_execs_with_loops']} WID executions) ---")
        print(f"{'Failures':>8} | {'Trial Results (bytes)':^80} | {'Average':>8}")
        print("-" * 105)

        for n_fail in failure_counts:
            trial_results = simulate_failures(trace, n_fail, num_trials)
            avg = sum(trial_results) / len(trial_results)
            trials_str = ', '.join(str(r) for r in trial_results)
            print(f"{n_fail:>8} | {trials_str:<80} | {avg:>8.1f}")

    print("\n\n" + "=" * 120)
    print("RESULTS: Version D - Optimized (Value-Only) Without Inner Loops")
    print("=" * 120)

    for bm_name in benchmarks:
        if bm_name not in all_results:
            continue
        result = all_results[bm_name]
        trace = result['trace_opt_no_loops']

        print(f"\n--- {bm_name} (base={result['base_opt_no_loops']} bytes, "
              f"{result['num_wids']} WID executions) ---")
        print(f"{'Failures':>8} | {'Trial Results (bytes)':^80} | {'Average':>8}")
        print("-" * 105)

        for n_fail in failure_counts:
            trial_results = simulate_failures(trace, n_fail, num_trials)
            avg = sum(trial_results) / len(trial_results)
            trials_str = ', '.join(str(r) for r in trial_results)
            print(f"{n_fail:>8} | {trials_str:<80} | {avg:>8.1f}")

    # Summary table
    print("\n\n" + "=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)

    print(f"\n{'Benchmark':>12} | {'WIDs':>5} | {'Current+Loop':>13} | {'Current-Loop':>13} | {'Opt+Loop':>10} | {'Opt-Loop':>10}")
    print("-" * 75)
    for bm_name in benchmarks:
        if bm_name not in all_results:
            continue
        r = all_results[bm_name]
        print(f"{bm_name:>12} | {r['num_wids']:>5} | {r['base_with_loops']:>13} | {r['base_no_loops']:>13} | {r['base_opt_with_loops']:>10} | {r['base_opt_no_loops']:>10}")


if __name__ == '__main__':
    main()
