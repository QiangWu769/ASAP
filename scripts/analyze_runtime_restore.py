#!/usr/bin/env python3
"""
Runtime restore volume analysis at different execution progress.

Considers loops and array writes: at X% execution progress,
how many bytes of data (including array elements) would need
to be restored if power failed at that point.
"""

# Each benchmark modeled as a sequence of write operations
# with loop counts and cumulative data written

BENCHMARKS = {
    "ar": {
        "description": "Activity Recognition",
        "total_loop_iters": 562,  # warmup(3) + train_stat(16×(3+1+1+1)=96) + train_move(96) + recog(8×(3+1+1+1+1)=48) + misc
        "phases": [
            # (name, n_iterations, bytes_per_iter, cumulative_new_bytes_desc)
            ("warmup", 3, 2, "seed(2B) per sample"),
            ("train_stat_acquire", 48, 4, "sampleWindow element(4B)"),
            ("train_stat_transform", 16, 4, "sampleWindow element(4B)"),
            ("train_stat_featurize", 16, 4, "features(4B)"),
            ("train_stat_store", 16, 8, "model.stationary[i](8B)"),
            ("train_move_acquire", 48, 4, "sampleWindow(4B)"),
            ("train_move_transform", 16, 4, "sampleWindow(4B)"),
            ("train_move_featurize", 16, 4, "features(4B)"),
            ("train_move_store", 16, 8, "model.moving[i](8B)"),
            ("recog_acquire", 24, 4, "sampleWindow(4B)"),
            ("recog_classify", 8, 4, "stats fields(4B)"),
            ("recog_stats", 8, 6, "stats(6B)"),
        ]
    },
    "bc": {
        "description": "Bit Count",
        "total_loop_iters": 700,
        "phases": [
            ("init", 1, 16, "n_0..n_6(14B) + func(2B)"),
            ("func_loop", 7, 6, "func(2B) + seed(4B)"),
            ("bit_count_iters", 100, 8, "n_0(2B) + seed(4B) + iter(2B)"),
            ("bitcount_iters", 100, 8, "n_1(2B) + seed(4B) + iter(2B)"),
            ("ntbl_bitcnt_iters", 100, 8, "n_2(2B) + seed(4B) + iter(2B)"),
            ("ntbl_bitcount_iters", 100, 8, "n_3(2B) + seed(4B) + iter(2B)"),
            ("BW_btbl_iters", 100, 8, "n_4(2B) + seed(4B) + iter(2B)"),
            ("AR_btbl_iters", 100, 8, "n_5(2B) + seed(4B) + iter(2B)"),
            ("bit_shifter_iters", 100, 8, "n_6(2B) + seed(4B) + iter(2B)"),
        ]
    },
    "cf": {
        "description": "Cuckoo Filter",
        "total_loop_iters": 384,  # init(128) + inserts(32×5) + lookups(32×3)
        "phases": [
            ("filter_init", 128, 2, "filter[i](2B)"),
            ("insert_gen", 32, 2, "key(2B)"),
            ("insert_hash", 32, 6, "fingerprint(2B) + index1(2B) + index2(2B)"),
            ("insert_write", 32, 4, "filter[idx](2B) + inserts(2B)"),
            ("insert_reloc", 32, 4, "filter[victim](2B) + reloc_count(2B)"),
            ("lookup_gen", 32, 2, "key(2B)"),
            ("lookup_hash", 32, 6, "fp(2B) + idx1(2B) + idx2(2B)"),
            ("lookup_check", 32, 2, "member(2B)"),
        ]
    },
    "conv": {
        "description": "1D Convolution",
        "total_loop_iters": 4563,  # vec_init(200) + out_init(181) + conv(181×20+181)
        "phases": [
            ("vec_init", 200, 2, "vec[i]=i (2B per element)"),
            ("out_init", 181, 2, "out[i]=0 (2B per element)"),
            ("conv_outer", 181, 2, "out[i]=temp (2B per element)"),
            ("conv_inner", 3620, 2, "temp+=vec[i+j] (2B temp accumulate)"),
        ]
    },
    "crc": {
        "description": "CRC-16",
        "total_loop_iters": 2393,  # crcSlow(9×8) + crcInit(256×8) + crcFast(9)
        "phases": [
            ("crcSlow_outer", 9, 2, "remainder(2B)"),
            ("crcSlow_inner", 72, 2, "remainder(2B) per bit"),
            ("crcInit_outer", 256, 4, "crcTable[div](2B) + remainder(2B)"),
            ("crcInit_inner", 2048, 2, "remainder(2B) per bit"),
            ("crcFast", 9, 4, "remainder(2B) + data(2B)"),
        ]
    },
    "adpcm_de": {
        "description": "ADPCM Decoder",
        "total_loop_iters": 128,
        "phases": [
            ("init", 1, 6, "valpred(2B) + index(2B) + step(2B)"),
            ("decode_loop", 128, 10, "sbuf[out](2B) + valpred(2B) + index(2B) + step(2B) + misc(2B)"),
        ]
    },
    "adpcm_en": {
        "description": "ADPCM Encoder",
        "total_loop_iters": 128,
        "phases": [
            ("init", 1, 6, "valpred(2B) + index(2B) + step(2B)"),
            ("encode_loop", 128, 10, "output(2B) + valpred(2B) + index(2B) + step(2B) + delta(2B)"),
        ]
    },
}


def compute_restore_at_progress(bench_data, progress_pcts):
    """Compute cumulative data written at each progress point.
    
    For restore, we need the UNIQUE data that would need to be restored:
    - Scalar variables: only the LATEST value matters (not cumulative writes)
    - Array elements: each element needs to be restored individually
    """
    phases = bench_data["phases"]
    
    # Build execution timeline: list of (iteration_index, bytes_written_this_step, is_new_unique_data)
    timeline = []
    for phase_name, n_iters, bytes_per, desc in phases:
        # Determine if this phase writes to NEW unique locations or overwrites existing
        is_array = any(kw in desc for kw in ['[i]', '[idx]', '[div]', '[out]', '[victim]', 'element', 'Table'])
        
        for i in range(n_iters):
            if is_array:
                timeline.append((phase_name, bytes_per, True))  # new unique array element
            else:
                timeline.append((phase_name, bytes_per, False))  # overwrites same scalar
    
    total_steps = len(timeline)
    results = {}
    
    for pct in progress_pcts:
        target = int(total_steps * pct / 100)
        
        # Count unique data that would need restoration
        scalar_vars = {}  # {phase_name: latest_size}
        array_bytes = 0   # cumulative array elements
        
        for idx in range(target):
            phase, size, is_new = timeline[idx]
            if is_new:
                array_bytes += size
            else:
                scalar_vars[phase] = size
        
        scalar_total = sum(scalar_vars.values())
        total = scalar_total + array_bytes
        results[pct] = {"scalar": scalar_total, "array": array_bytes, "total": total}
    
    return results


def main():
    progress_pcts = list(range(5, 101, 5))  # 5%, 10%, 15%, ..., 100%
    # Add intermediate points for finer resolution
    progress_pcts = sorted(set(progress_pcts + [7, 12, 17, 22, 27, 33, 37, 42, 47]))  # ~2-5% resolution
    
    print("=" * 100)
    print("Runtime Restore Volume at Different Execution Progress")
    print("(Considering loops, arrays, and scalar overwrites)")
    print("=" * 100)
    
    for bench, data in BENCHMARKS.items():
        results = compute_restore_at_progress(data, progress_pcts)
        
        phases_str = ", ".join(f"{p[0]}({p[1]}×{p[2]}B)" for p in data["phases"])
        print(f"\n{bench} ({data['description']})")
        print(f"  Phases: {phases_str}")
        print(f"  {'Progress':>8s}  {'Scalar':>8s}  {'Array':>8s}  {'TOTAL':>8s}")
        print(f"  {'-'*40}")
        for pct in progress_pcts:
            r = results[pct]
            print(f"  {pct:>7d}%  {r['scalar']:>7d}B  {r['array']:>7d}B  {r['total']:>7d}B")
    
    # Export CSV
    import csv
    with open("runtime_restore_progress.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["benchmark", "progress_pct", "scalar_bytes", "array_bytes", "total_bytes"])
        for bench, data in BENCHMARKS.items():
            results = compute_restore_at_progress(data, progress_pcts)
            for pct in progress_pcts:
                r = results[pct]
                w.writerow([bench, pct, r["scalar"], r["array"], r["total"]])
    print(f"\nCSV exported to runtime_restore_progress.csv")


if __name__ == "__main__":
    main()
