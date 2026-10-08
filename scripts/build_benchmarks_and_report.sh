#!/bin/bash
# ============================================================================
# 为 ar/bc/cf/conv/crc/adpcm_de/adpcm_en 生成 pure + ASAP 版本
# 并从工具链中提取备份点密度统计
# 源码路径与 Makefile 一致
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Makefile 中 BENCHMARK -> 源文件路径
# adpcm_de=adpcm(decode), adpcm_en=adpcm_encode
declare -A SRC_MAP
SRC_MAP[ar]="Benchmarks/ar/main_ar.c"
SRC_MAP[bc]="Benchmarks/bc/main_bc.c"
SRC_MAP[cf]="Benchmarks/cf/main_cf_plain.c"
SRC_MAP[conv]="Benchmarks/conv/main_conv_plain.c"
SRC_MAP[crc]="Benchmarks/crc/main_crc_test_16.c"
SRC_MAP[adpcm_de]="Benchmarks/adpcm_decode/main_adpcm.c"
SRC_MAP[adpcm_en]="Benchmarks/adpcm_encode/main_adpcm_encode.c"

# 对应 Makefile BENCHMARK 名（用于 make）
declare -A MAKE_BENCH
MAKE_BENCH[ar]=ar
MAKE_BENCH[bc]=bc
MAKE_BENCH[cf]=cf
MAKE_BENCH[conv]=conv
MAKE_BENCH[crc]=crc
MAKE_BENCH[adpcm_de]=adpcm
MAKE_BENCH[adpcm_en]=adpcm_encode

# Include 目录（源码所在目录）
get_inc_dir() {
    echo "$(dirname "$1")"
}

# 编译 pure 版本（无 ASAP）
compile_pure() {
    local name=$1
    local src=$2
    local out="${name}_pure.out"
    local inc=$(get_inc_dir "$src")

    if [ -f "$out" ]; then
        echo "  [跳过] $out 已存在"
        return 0
    fi

    echo "  [编译] $out <- $src"
    if msp430-elf-gcc -mmcu=msp430fr5969 -O0 -g -DTIMER=0 -I "$inc" -I Benchmarks "$src" -o "$out" 2>/dev/null; then
        echo "  [完成] $out ($(ls -lh "$out" 2>/dev/null | awk '{print $5}'))"
    else
        echo "  [失败] $name pure 编译失败"
        return 1
    fi
}

# 编译 ASAP 版本（make BENCHMARK=xx）
# 注：为获取备份点统计必须执行 make，因此不跳过
compile_asap() {
    local make_bench=$1
    local out="${make_bench}_asap_no_timer.out"

    echo "  [编译] ASAP: make BENCHMARK=$make_bench"
    make clean >/dev/null 2>&1
    if make BENCHMARK="$make_bench" TIMER=0; then
        echo "  [完成] $out"
    else
        echo "  [失败] $make_bench ASAP 编译失败"
        return 1
    fi
}

# 提取备份点统计（从 build/）
extract_stats_table() {
    python3 scripts/extract_backup_stats.py --build-dir build --table-row 2>/dev/null
}
extract_stats_detail() {
    python3 scripts/extract_backup_stats.py --build-dir build 2>/dev/null
}

# 报表输出
REPORT_FILE="BACKUP_POINT_REPORT.txt"
TABLE_FILE="BACKUP_POINT_TABLE.txt"
echo "=== ASAP Benchmark 备份点密度报表 ===" | tee "$REPORT_FILE"
echo "生成时间: $(date)" | tee -a "$REPORT_FILE"
echo "" | tee -a "$REPORT_FILE"

# 表格表头
echo -e "Benchmark\t备份点数\t每点字节\tFRAM槽位\tFRAM字节\t指令数\t平均间距" > "$TABLE_FILE"
ALL_ROWS=""

for bench in ar bc cf conv crc adpcm_de adpcm_en; do
    src=${SRC_MAP[$bench]}
    make_bench=${MAKE_BENCH[$bench]}

    if [ -z "$src" ] || [ ! -f "$src" ]; then
        echo "[跳过] $bench: 源文件不存在 ($src)"
        continue
    fi

    echo "----------------------------------------"
    echo "Benchmark: $bench (src=$src, make=$make_bench)"
    echo "----------------------------------------"

    # 1. Pure
    echo "[Pure]"
    compile_pure "$bench" "$src" || true

    # 2. ASAP（会覆盖 build/）
    echo "[ASAP]"
    compile_asap "$make_bench" || true

    # 3. 统计（仅在 ASAP 成功且 build 存在时）
    if [ -f "build/candidates.json" ] && [ -f "build/fram_slots.json" ]; then
        echo "[统计]"
        stats_detail=$(extract_stats_detail)
        stats_table=$(extract_stats_table)
        echo "$stats_detail"
        echo "" >> "$REPORT_FILE"
        echo "--- $bench ---" >> "$REPORT_FILE"
        echo "$stats_detail" >> "$REPORT_FILE"
        # 追加到表格：bench + tab + stats(6列)
        echo -e "${bench}\t${stats_table}" >> "$TABLE_FILE"
    fi
    echo ""
done

echo "========================================"
echo "备份点密度汇总表 ($TABLE_FILE):"
echo "========================================"
column -t -s $'\t' "$TABLE_FILE" 2>/dev/null || cat "$TABLE_FILE"
echo ""
echo "报表已写入: $REPORT_FILE"
echo "========================================"
