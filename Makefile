# ============================================================================
# ASAP 完整编译流程 - 新版本（13 Stages）
# ============================================================================
# 从C源码到最终.out文件的完整自动化流程
# 按地址分配FRAM，覆盖写同一槽位，表驱动恢复逻辑
# ============================================================================

# ===== 配置变量 =====
MCU        ?= msp430fr5969
CFLAGS     ?= -O0 -g
BUILD_DIR  ?= build

# Benchmark选择（make BENCHMARK=ar/cf/bc/crc/conv）
BENCHMARK  ?= ar

# Timer选择（make TIMER=0 或 TIMER=1）
TIMER      ?= 0

# 自动生成输出文件名：benchmark_asap_[no_]timer[_XXk].out
ifeq ($(TIMER), 0)
    OUTPUT := $(BENCHMARK)_asap_no_timer.out
else
    # 根据 TIMER_VALUE 生成后缀 (10000->10k, 20000->20k, 40000->40k)
    ifeq ($(TIMER_VALUE), 10000)
        OUTPUT := $(BENCHMARK)_asap_timer_10k.out
    else ifeq ($(TIMER_VALUE), 20000)
        OUTPUT := $(BENCHMARK)_asap_timer_20k.out
    else ifeq ($(TIMER_VALUE), 40000)
        OUTPUT := $(BENCHMARK)_asap_timer_40k.out
    else
        OUTPUT := $(BENCHMARK)_asap_timer.out
    endif
endif

# 根据BENCHMARK自动选择源文件
ifeq ($(BENCHMARK), ar)
    SRC := Benchmarks/ar/main_ar.c
else ifeq ($(BENCHMARK), cf)
    SRC := Benchmarks/cf/main_cf_plain.c
else ifeq ($(BENCHMARK), bc)
    SRC := Benchmarks/bc/main_bc.c
else ifeq ($(BENCHMARK), crc)
    SRC := Benchmarks/crc/main_crc_test_16.c
else ifeq ($(BENCHMARK), crc32)
    SRC := Benchmarks/crc/main_crc_test_32.c
else ifeq ($(BENCHMARK), conv)
    SRC := Benchmarks/conv/main_conv_plain.c
else ifeq ($(BENCHMARK), adpcm)
    SRC := Benchmarks/adpcm_decode/main_adpcm.c
else ifeq ($(BENCHMARK), adpcm_encode)
    SRC := Benchmarks/adpcm_encode/main_adpcm_encode.c
else ifeq ($(BENCHMARK), sha)
    SRC := Benchmarks/sha/main_sha.c
else ifeq ($(BENCHMARK), dnn)
    SRC := Benchmarks/dnn/main_dnn.c
else
    SRC := $(BENCHMARK)
endif

# 断电模拟选项（Power Failure Simulation）
# 设置为1启用断电模拟，0禁用
PF_SIMULATION ?= 0
ifeq ($(PF_SIMULATION), 1)
    CFLAGS += -DPF_SIMULATION
endif

# Timer断电模拟开关（Chinchilla风格）
# 用于 main_bc_chinchilla.c: TIMER=0正常运行, TIMER=1周期性断电
TIMER ?= 0
TIMER_VALUE ?= 40000
ifeq ($(TIMER), 1)
    CFLAGS += -DTIMER=1 -DTIMER_VALUE=$(TIMER_VALUE)
else
    CFLAGS += -DTIMER=0
endif

# 工具链
COMPILER   ?= msp430-elf-gcc
OBJDUMP    ?= msp430-elf-objdump

# Python脚本路径
STAGE1     := Compiler/stage1_compile_to_asm.py
STAGE2B    := Compiler/stage2b_make_idempotent.py
STAGE2C    := Compiler/stage2c_eliminate_indirect_addressing.py
STAGE2     := Compiler/stage2_analyze_functions.py
STAGE2_5   := Compiler/stage2_5_analyze_calls.py
STAGE1C    := Compiler/stage1c_inject_entry_checkpoint.py
STAGE3     := Compiler/stage3_analyze_writes.py
STAGE4     := Compiler/stage4_allocate_fram.py
STAGE5     := Compiler/stage5_inject_backup.py
STAGE5B    := Compiler/stage5b_inject_main_restore.py
STAGE5D    := Compiler/stage5d_redirect_indirect_slots.py
STAGE7     := Compiler/stage7_extract_wid_pc.py
STAGE8     := Compiler/stage8_analyze_reads_writes_v2.py
STAGE9     := Compiler/stage9_analyze_lifetime.py
STAGE9B    := Compiler/stage9b_build_call_graph.py
STAGE10    := Compiler/stage10_merge_pc_ranges.py
STAGE11    := Compiler/stage11_generate_restore_dedup.py

# 新增：循环数组多槽位支持
STAGE3B    := Compiler/stage3b_detect_loop_array.py
STAGE4B    := Compiler/stage4b_allocate_array_mirror.py
STAGE5E    := Compiler/stage5e_inject_array_mirror.py
STAGE11B   := Compiler/stage11b_array_restore.py

# 中间文件
ASM_SYM           := $(BUILD_DIR)/A_sym.s
ASM_IDEMPOTENT    := $(BUILD_DIR)/A_idempotent.s
ASM_DIRECT_ADDR   := $(BUILD_DIR)/A_direct_addr.s
FUNC_INFO         := $(BUILD_DIR)/function_info.json
CALL_INFO         := $(BUILD_DIR)/call_info.json
CANDIDATES        := $(BUILD_DIR)/candidates.json
FRAM_SLOTS        := $(BUILD_DIR)/fram_slots.json
FRAM_SYMBOLS_LD   := $(BUILD_DIR)/fram_symbols.ld
ASM_INSTRUMENTED  := $(BUILD_DIR)/A_instrumented.s
ASM_REDIRECTED    := $(BUILD_DIR)/A_redirected.s
REDIRECT_MAP      := $(BUILD_DIR)/redirect_map.json
FIRMWARE_TEMP     := $(BUILD_DIR)/firmware_temp.elf
WID_PC_MAP        := $(BUILD_DIR)/wid_pc_map.json
READS_WRITES      := $(BUILD_DIR)/reads_writes.json
LIFETIME_DATA     := $(BUILD_DIR)/lifetime_data.json
CALL_GRAPH        := $(BUILD_DIR)/call_graph.json
PC_RANGES         := $(BUILD_DIR)/pc_ranges.json
RESTORE_ASM       := $(BUILD_DIR)/asap_restore.s

# 循环数组镜像相关
LOOP_ARRAYS       := $(BUILD_DIR)/loop_arrays.json
ASM_ARRAY_MIRROR  := $(BUILD_DIR)/A_array_mirror.s

# 目标文件
MAIN_O            := $(BUILD_DIR)/main.o
BOOTLOADER_O      := $(BUILD_DIR)/bootloader.o
RESTORE_O         := $(BUILD_DIR)/asap_restore.o

# 链接脚本
LINKER_SCRIPT     := Runtime/src/port/msp430/msp430fr5969_bootloader.ld

# 配置文件
BC_CONFIG         := Compiler/bc_core_config.json

# 断电模拟（可选）
ENABLE_POWER_SIM  ?= 0
FAIL_AT_WID       ?= W010

# ===== Phony目标 =====
.PHONY: all clean help show \
	stage1 stage2 stage3 stage4 stage5 stage5b stage5c stage5d stage6 stage7 \
	stage8 stage9 stage10 stage11 stage12 stage13

# ===== 默认目标 =====
all: $(OUTPUT)
	@echo ""
	@echo "✅ =============================================="
	@echo "✅  ASAP完整编译成功！"
	@echo "✅ =============================================="
	@echo "   最终固件: $(OUTPUT)"
	@ls -lh $(OUTPUT) 2>/dev/null || true
	@echo ""

# ===== Stage 1: C源码 → 汇编 =====
stage1: $(ASM_SYM)
$(ASM_SYM): $(SRC)
	@echo ""
	@echo "[Stage 1/14] 编译C源码到汇编"
	@echo "  输入: $(SRC)"
	@echo "  输出: $(ASM_SYM)"
	@mkdir -p $(BUILD_DIR)
	python3 $(STAGE1) $(SRC) \
		--output $(ASM_SYM) \
		--compiler $(COMPILER) \
		--mcu $(MCU) \
		--cflags "$(CFLAGS)"
	@echo "  ✓ Stage 1 完成"

# ===== Stage 2b: 幂等化转换 =====
stage2b: $(ASM_IDEMPOTENT)
$(ASM_IDEMPOTENT): $(ASM_SYM)
	@echo ""
	@echo "[Stage 2b/15] 幂等化转换（inc/dec → load-add-store）"
	@echo "  输入: $(ASM_SYM)"
	@echo "  输出: $(ASM_IDEMPOTENT)"
	python3 $(STAGE2B) $(ASM_SYM) --output $(ASM_IDEMPOTENT)
	@echo "  ✓ Stage 2b 完成"

# ===== Stage 2: 分析函数信息 =====
stage2: $(FUNC_INFO)
$(FUNC_INFO): $(ASM_IDEMPOTENT)
	@echo ""
	@echo "[Stage 2/15] 分析函数信息"
	@echo "  输入: $(ASM_IDEMPOTENT)"
	@echo "  输出: $(FUNC_INFO)"
	python3 $(STAGE2) $(ASM_IDEMPOTENT) --output $(FUNC_INFO)
	@echo "  ✓ Stage 2 完成"

# ===== Stage 2.5: 分析函数调用和参数传递 =====
stage2_5: $(CALL_INFO)
$(CALL_INFO): $(ASM_IDEMPOTENT) $(FUNC_INFO)
	@echo ""
	@echo "[Stage 2.5/15] 分析函数调用和参数传递（用于间接栈写入检测）"
	@echo "  输入: $(ASM_IDEMPOTENT), $(FUNC_INFO)"
	@echo "  输出: $(CALL_INFO)"
	python3 $(STAGE2_5) $(ASM_IDEMPOTENT) \
		--functions $(FUNC_INFO) \
		--output $(CALL_INFO)
	@echo "  ✓ Stage 2.5 完成"

# ===== Stage 1c: 注入函数入口检查点（消除CALL盲区） =====
stage1c: $(ASM_IDEMPOTENT) $(FUNC_INFO)
	@echo ""
	@echo "[Stage 1c/16] 注入函数入口检查点（消除CALL前盲区）"
	@echo "  输入: $(ASM_IDEMPOTENT), $(FUNC_INFO)"
	python3 $(STAGE1C) $(ASM_IDEMPOTENT) \
		--functions $(FUNC_INFO) \
		--output $(ASM_IDEMPOTENT)
	@echo "  ✓ Stage 1c 完成"

# ===== Stage 2c: 消除间接寻址 =====
stage2c: $(ASM_DIRECT_ADDR)
$(ASM_DIRECT_ADDR): $(ASM_IDEMPOTENT) $(FUNC_INFO)
	@echo ""
	@echo "[Stage 2c/15] 消除间接寻址（转换为直接栈寻址）"
	@echo "  输入: $(ASM_IDEMPOTENT), $(FUNC_INFO)"
	@echo "  输出: $(ASM_DIRECT_ADDR)"
	python3 $(STAGE2C) $(ASM_IDEMPOTENT) \
		--function-info $(FUNC_INFO) \
		--output $(ASM_DIRECT_ADDR)
	@echo "  ✓ Stage 2c 完成"

# ===== Stage 3: 识别关键写（排除输出，支持数组+间接栈写入检测） =====
stage3: $(CANDIDATES)
$(CANDIDATES): $(ASM_IDEMPOTENT) $(FUNC_INFO) $(CALL_INFO) | stage1c
	@echo ""
	@echo "[Stage 3/15] 识别关键写（排除输出，支持数组+间接栈写入检测）"
	@echo "  输入: $(ASM_IDEMPOTENT), $(FUNC_INFO), $(CALL_INFO)"
	@echo "  输出: $(CANDIDATES)"
	python3 Compiler/stage3_analyze_writes_array.py $(ASM_IDEMPOTENT) \
		--functions $(FUNC_INFO) \
		--call-info $(CALL_INFO) \
		--config $(BC_CONFIG) \
		--output $(CANDIDATES) \
		--enable-array-detection
	@echo "  ✓ Stage 3 完成"

# ===== Stage 3b: 检测循环数组写入 =====
stage3b: $(LOOP_ARRAYS)
$(LOOP_ARRAYS): $(ASM_IDEMPOTENT) $(CANDIDATES)
	@echo ""
	@echo "[Stage 3b/16] 检测循环数组写入模式"
	@echo "  输入: $(ASM_IDEMPOTENT), $(CANDIDATES)"
	@echo "  输出: $(LOOP_ARRAYS)"
	python3 $(STAGE3B) \
		--asm $(ASM_IDEMPOTENT) \
		--candidates $(CANDIDATES) \
		--output $(LOOP_ARRAYS)
	@echo "  ✓ Stage 3b 完成"

# ===== Stage 4: 分配FRAM槽位（按地址，支持数组） =====
stage4: $(FRAM_SLOTS) $(FRAM_SYMBOLS_LD)
$(FRAM_SLOTS) $(FRAM_SYMBOLS_LD): $(CANDIDATES)
	@echo ""
	@echo "[Stage 4/14] 分配FRAM槽位（按地址，支持数组连续分配）"
	@echo "  输入: $(CANDIDATES)"
	@echo "  输出: $(FRAM_SLOTS), $(FRAM_SYMBOLS_LD)"
	python3 Compiler/stage4_allocate_fram_array.py $(CANDIDATES) \
		--output $(FRAM_SLOTS) \
		--linker $(FRAM_SYMBOLS_LD)
	@echo "  ✓ Stage 4 完成"

# ===== Stage 4b: 分配循环数组FRAM镜像空间 =====
stage4b: stage3b $(LOOP_ARRAYS) $(FRAM_SLOTS)
	@echo ""
	@echo "[Stage 4b/16] 分配循环数组FRAM镜像空间"
	@echo "  输入: $(LOOP_ARRAYS), $(FRAM_SLOTS)"
	python3 $(STAGE4B) \
		--loop-arrays $(LOOP_ARRAYS) \
		--fram-slots $(FRAM_SLOTS) \
		--symbols-ld $(FRAM_SYMBOLS_LD)
	@echo "  ✓ Stage 4b 完成"

# ===== Stage 5: 插桩备份（支持数组索引感知） =====
# 【修复】添加$(LOOP_ARRAYS)依赖，用于跳过全局数组的INDIRECT_STACK备份
stage5: $(ASM_INSTRUMENTED)
$(ASM_INSTRUMENTED): $(ASM_IDEMPOTENT) $(CANDIDATES) $(FRAM_SLOTS) $(LOOP_ARRAYS)
	@echo ""
	@echo "[Stage 5/15] 插桩备份逻辑（支持数组索引感知）"
	@echo "  输入: $(ASM_IDEMPOTENT), $(CANDIDATES), $(FRAM_SLOTS)"
	@echo "  输出: $(ASM_INSTRUMENTED)"
	python3 Compiler/stage5_inject_backup_array.py $(ASM_IDEMPOTENT) \
		--candidates $(CANDIDATES) \
		--fram-slots $(FRAM_SLOTS) \
		--output $(ASM_INSTRUMENTED) \
		--enable-array-backup \
		--loop-arrays $(LOOP_ARRAYS)
	@echo "  ✓ Stage 5 插桩完成"
	@echo ""
	@echo "[Stage 5-opt] SP备份优化（删除冗余SP备份指令）"
	python3 Compiler/stage5_optimize_sp.py $(ASM_INSTRUMENTED) --output $(ASM_INSTRUMENTED)
	@echo "  ✓ Stage 5 完成"

# ===== Stage 5g: 重排非幂等操作的备份顺序 =====
# 解决：INC/ADD等操作的备份应该在WID标签之前，避免断电竞争条件
STAGE5G    := Compiler/stage5g_reorder_nonidempotent.py
stage5g: stage5 $(ASM_INSTRUMENTED)
	@echo ""
	@echo "[Stage 5g/17] 重排非幂等操作的备份顺序（移至WID标签前）"
	@echo "  输入/输出: $(ASM_INSTRUMENTED)"
	python3 $(STAGE5G) \
		--input $(ASM_INSTRUMENTED) \
		--output $(ASM_INSTRUMENTED)
	@touch $(ASM_INSTRUMENTED)
	@echo "  ✓ Stage 5g 完成"

# ===== Stage 5b: 在main外设初始化后插入PC检查逻辑 =====
stage5b: stage5g
	@echo ""
	@echo "[Stage 5b/13] 在main外设初始化后插入热启动PC检查逻辑"
	@echo "  输入/输出: $(ASM_INSTRUMENTED)"
	python3 $(STAGE5B) $(ASM_INSTRUMENTED)
	@touch $(ASM_INSTRUMENTED)
	@echo "  ✓ Stage 5b 完成"

# ===== Stage 5c: 在子函数入口插入返回地址备份 =====
stage5c: stage5b stage4b
	@echo ""
	@echo "[Stage 5c/13] 在子函数入口插入返回地址备份（支持子函数断电恢复）"
	@echo "  输入/输出: $(ASM_INSTRUMENTED)"
	python3 Compiler/stage5c_inject_return_addr_backup.py $(ASM_INSTRUMENTED) \
		--functions $(FUNC_INFO) \
		--config $(BC_CONFIG) \
		--fram-slots $(FRAM_SLOTS)
	@touch $(ASM_INSTRUMENTED)
	@echo "  ✓ Stage 5c 完成"

# ===== Stage 5e: 注入循环数组镜像写入 =====
stage5e: stage5c stage4b $(ASM_INSTRUMENTED)
	@echo ""
	@echo "[Stage 5e/16] 注入循环数组镜像写入代码"
	@echo "  输入: $(ASM_INSTRUMENTED), $(LOOP_ARRAYS), $(FRAM_SLOTS)"
	@echo "  输出: $(ASM_ARRAY_MIRROR)"
	python3 $(STAGE5E) \
		--input $(ASM_INSTRUMENTED) \
		--loop-arrays $(LOOP_ARRAYS) \
		--fram-slots $(FRAM_SLOTS) \
		--output $(ASM_ARRAY_MIRROR)
	@# 用镜像版本替换原文件
	cp $(ASM_ARRAY_MIRROR) $(ASM_INSTRUMENTED)
	@echo "  ✓ Stage 5e 完成"

# ===== Stage 5f: 备份下一条写入的寄存器 =====
# 解决：WID设置后紧跟的写入使用寄存器，恢复时寄存器是垃圾值
# 【注意】必须在stage5d之后执行，因为stage5d生成A_redirected.s
STAGE5F    := Compiler/stage5f_backup_next_reg.py
WID_REG_MAP := $(BUILD_DIR)/wid_reg_map.json
stage5f: stage5d $(ASM_REDIRECTED)
	@echo ""
	@echo "[Stage 5f/17] 备份下一条写入的寄存器"
	@echo "  输入: $(ASM_REDIRECTED), $(FRAM_SLOTS)"
	@echo "  输出: $(ASM_REDIRECTED), $(WID_REG_MAP)"
	python3 $(STAGE5F) \
		--input $(ASM_REDIRECTED) \
		--output $(ASM_REDIRECTED) \
		--fram-slots $(FRAM_SLOTS) \
		--fram-symbols $(FRAM_SYMBOLS_LD) \
		--reg-map $(WID_REG_MAP)
	@echo "  ✓ Stage 5f 完成"

# ===== Stage 6: 编译临时固件（用于PC提取）=====
stage6: $(FIRMWARE_TEMP)
$(FIRMWARE_TEMP): stage5f $(ASM_REDIRECTED) $(FRAM_SYMBOLS_LD)
	@echo ""
	@echo "[Stage 6/13] 编译临时固件（用于PC提取，使用bootloader.ld）"
	@echo "  输入: $(ASM_REDIRECTED)（已插桩+寄存器备份）"
	# 先编译符号文件（如果存在）
	@if [ -f build/func_sp_symbols.s ]; then \
		$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c build/func_sp_symbols.s -o build/func_sp_symbols.o; \
	fi
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(ASM_REDIRECTED) -o $(MAIN_O)
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c Runtime/asap_restore_stub.s -o build/asap_restore_stub.o
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) \
		-nostartfiles \
		-T Runtime/src/port/msp430/msp430fr5969_bootloader.ld \
		-Wl,--just-symbols=$(FRAM_SYMBOLS_LD) \
		-o $(FIRMWARE_TEMP) \
		build/bootloader_restore.o \
		$(MAIN_O) \
		build/asap_restore_stub.o \
		build/func_sp_symbols.o \
		-lgcc
	@echo "  ✓ Stage 6 完成"

# ===== Stage 7: 提取WID→PC映射 =====
stage7: $(WID_PC_MAP)
$(WID_PC_MAP): $(FIRMWARE_TEMP)
	@echo ""
	@echo "[Stage 7/13] 提取WID→PC映射"
	@echo "  输入: $(FIRMWARE_TEMP)"
	@echo "  输出: $(WID_PC_MAP)"
	python3 $(STAGE7) $(FIRMWARE_TEMP) \
		--output $(WID_PC_MAP) \
		--objdump $(OBJDUMP)
	@echo "  ✓ Stage 7 完成"

# ===== Stage 8: 分析读写操作（从反汇编） =====
stage8: $(READS_WRITES)
$(READS_WRITES): $(FIRMWARE_TEMP)
	@echo ""
	@echo "[Stage 8/13] 分析读写操作（从反汇编，带PC）"
	@echo "  输入: $(FIRMWARE_TEMP)"
	@echo "  输出: $(READS_WRITES)"
	python3 $(STAGE8) $(FIRMWARE_TEMP) \
		--output $(READS_WRITES)
	@echo "  ✓ Stage 8 完成"

# ===== Stage 9: 生命周期分析（基于地址） =====
stage9: $(LIFETIME_DATA)
$(LIFETIME_DATA): $(READS_WRITES) $(WID_PC_MAP) $(CANDIDATES)
	@echo ""
	@echo "[Stage 9/13] 生命周期分析（基于地址）"
	@echo "  输入: $(READS_WRITES), $(WID_PC_MAP), $(CANDIDATES)"
	@echo "  输出: $(LIFETIME_DATA)"
	python3 $(STAGE9) \
		--reads-writes $(READS_WRITES) \
		--wid-pc-map $(WID_PC_MAP) \
		--candidates $(CANDIDATES) \
		--output $(LIFETIME_DATA)
	@echo "  ✓ Stage 9 完成"

# ===== Stage 9b: 构建函数调用图 =====
stage9b: $(CALL_GRAPH)
$(CALL_GRAPH): $(ASM_INSTRUMENTED) $(FUNC_INFO) $(CANDIDATES)
	@echo ""
	@echo "[Stage 9b/13] 构建函数调用图"
	@echo "  输入: $(ASM_INSTRUMENTED), $(FUNC_INFO), $(CANDIDATES)"
	@echo "  输出: $(CALL_GRAPH)"
	python3 $(STAGE9B) \
		--asm $(ASM_INSTRUMENTED) \
		--function-info $(FUNC_INFO) \
		--candidates $(CANDIDATES) \
		--output $(CALL_GRAPH)
	@echo "  ✓ Stage 9b 完成"

# ===== Stage 5d: 重定向间接地址的备份槽位 =====
stage5d: $(ASM_REDIRECTED)
$(ASM_REDIRECTED): stage5e $(ASM_INSTRUMENTED) $(CALL_GRAPH) $(FRAM_SLOTS) $(LOOP_ARRAYS)
	@echo ""
	@echo "[Stage 5d/14] 重定向间接地址的备份槽位"
	@echo "  输入: $(ASM_INSTRUMENTED), $(CALL_GRAPH), $(FRAM_SLOTS)"
	@echo "  输出: $(ASM_REDIRECTED)"
	python3 $(STAGE5D) \
		--input $(ASM_INSTRUMENTED) \
		--output $(ASM_REDIRECTED) \
		--call-graph $(CALL_GRAPH) \
		--fram-slots $(FRAM_SLOTS) \
		--redirect-map $(REDIRECT_MAP) \
		--loop-arrays $(LOOP_ARRAYS)
	@echo "  ✓ Stage 5d 完成"

# ===== Stage 10: 按WID生成恢复列表（支持调用栈和PC范围检查） =====
stage10: $(PC_RANGES)
$(PC_RANGES): $(LIFETIME_DATA) $(FRAM_SLOTS) $(CANDIDATES) $(CALL_GRAPH) $(WID_PC_MAP) $(REDIRECT_MAP)
	@echo ""
	@echo "[Stage 10/14] 按WID生成恢复列表（支持调用栈+重定向槽位）"
	@echo "  输入: $(LIFETIME_DATA), $(FRAM_SLOTS), $(CANDIDATES), $(CALL_GRAPH), $(REDIRECT_MAP)"
	@echo "  输出: $(PC_RANGES)"
	python3 $(STAGE10) \
		--lifetime $(LIFETIME_DATA) \
		--fram-slots $(FRAM_SLOTS) \
		--candidates $(CANDIDATES) \
		--call-graph $(CALL_GRAPH) \
		--redirect-map $(REDIRECT_MAP) \
		--wid-pc-map $(WID_PC_MAP) \
		--output $(PC_RANGES)
	@echo "  ✓ Stage 10 完成"

# ===== Stage 11: 生成恢复逻辑（去重优化版，含返回地址恢复） =====
stage11: $(RESTORE_ASM)
$(RESTORE_ASM): $(PC_RANGES) $(WID_PC_MAP) $(WID_REG_MAP)
	@echo ""
	@echo "[Stage 11/13] 生成恢复逻辑（去重优化，含返回地址+寄存器恢复）"
	@echo "  输入: $(PC_RANGES), $(WID_PC_MAP), $(FRAM_SLOTS), $(FUNC_INFO), $(WID_REG_MAP)"
	@echo "  输出: $(RESTORE_ASM)"
	python3 $(STAGE11) \
		--pc-ranges $(PC_RANGES) \
		--wid-pc-map $(WID_PC_MAP) \
		--fram-slots $(FRAM_SLOTS) \
		--function-info $(FUNC_INFO) \
		--wid-backup-regs $(WID_REG_MAP) \
		--output $(RESTORE_ASM) \
		--format asm
	@echo "  ✓ Stage 11 完成"

# ===== Stage 11b: 注入循环数组恢复代码 =====
stage11b: stage11 $(RESTORE_ASM)
	@echo ""
	@echo "[Stage 11b/16] 注入循环数组恢复代码"
	@echo "  输入/输出: $(RESTORE_ASM)"
	python3 $(STAGE11B) \
		--restore $(RESTORE_ASM) \
		--loop-arrays $(LOOP_ARRAYS) \
		--fram-slots $(FRAM_SLOTS)
	@echo "  ✓ Stage 11b 完成"

# ===== Stage 12: 编译恢复逻辑和符号文件 =====
stage12: $(RESTORE_O) build/func_sp_symbols.o
$(RESTORE_O): stage11b $(RESTORE_ASM) $(FRAM_SYMBOLS_LD)
	@echo ""
	@echo "[Stage 12/13] 编译恢复逻辑（恢复检查将在main开头通过汇编插桩）"
	@echo "  输入: $(RESTORE_ASM)"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(RESTORE_ASM) -o $(RESTORE_O)
	@echo "  ✓ Stage 12a 完成"

build/func_sp_symbols.o: build/func_sp_symbols.s
	@echo "  编译符号文件: build/func_sp_symbols.s"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c build/func_sp_symbols.s -o build/func_sp_symbols.o
	@echo "  ✓ Stage 12b 完成"

# ===== Stage 13: 最终链接，生成.out文件（两阶段） =====
stage13: $(OUTPUT)
$(OUTPUT): $(ASM_REDIRECTED) $(RESTORE_O) $(FRAM_SYMBOLS_LD)
	@echo ""
	@echo "[Stage 13/14] 最终链接，生成固件（两阶段，恢复检查在main开头）"
	@echo "  阶段1: 编译bootloader和main"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(ASM_REDIRECTED) -o $(MAIN_O)
	# 初步链接（使用bootloader.ld）
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) \
		-nostartfiles \
		-T $(LINKER_SCRIPT) \
		-Wl,--just-symbols=$(FRAM_SYMBOLS_LD) \
		-o $(OUTPUT) \
		build/bootloader_restore.o \
		$(MAIN_O) \
		$(RESTORE_O) \
		build/func_sp_symbols.o \
		-lgcc
	@echo "  阶段2: 从最终固件提取正确的PC映射"
	python3 $(STAGE7) $(OUTPUT) \
		--output $(WID_PC_MAP) \
		--objdump $(OBJDUMP)
	@echo "  阶段3: 重新生成恢复逻辑（使用正确PC，含返回地址+寄存器恢复）"
	python3 $(STAGE11) \
		--pc-ranges $(PC_RANGES) \
		--wid-pc-map $(WID_PC_MAP) \
		--fram-slots $(FRAM_SLOTS) \
		--function-info $(FUNC_INFO) \
		--wid-backup-regs $(WID_REG_MAP) \
		--output $(RESTORE_ASM) \
		--format asm
	@echo "  阶段3b: 注入循环数组恢复代码"
	python3 $(STAGE11B) \
		--restore $(RESTORE_ASM) \
		--loop-arrays $(LOOP_ARRAYS) \
		--fram-slots $(FRAM_SLOTS)
	@echo "  阶段4: 重新编译恢复逻辑"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(RESTORE_ASM) -o $(RESTORE_O)
	@echo "  阶段5: 重新编译bootloader和main"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c Runtime/bootloader_with_restore.s -o build/bootloader_restore.o
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(ASM_REDIRECTED) -o $(MAIN_O)
	# 最终链接（使用bootloader.ld和正确的PC映射）
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) \
		-nostartfiles \
		-T $(LINKER_SCRIPT) \
		-Wl,--just-symbols=$(FRAM_SYMBOLS_LD) \
		-o $(OUTPUT) \
		build/bootloader_restore.o \
		$(MAIN_O) \
		$(RESTORE_O) \
		build/func_sp_symbols.o \
		-lgcc
	@echo "  ✓ Stage 13 完成"

# ===================================================================
# 【新增】独立的Bootloader-CRT0架构编译流程
# 这是一个完全独立的实现，使用包含C初始化的自定义Bootloader
# 入口点: bootloader_entry（替代GCC的_start）
# ===================================================================

BOOTLOADER_CRT0_S = Runtime/bootloader_with_crt0_init.s
BOOTLOADER_CRT0_O = build/bootloader_crt0.o
BOOTLOADER_LD = Runtime/src/port/msp430/msp430fr5969_bootloader.ld
BOOTLOADER_OUT = firmware_bootloader_crt0.out

# 主要编译目标：使用Bootloader-CRT0架构
bootloader: stage1 stage2 stage3 stage4 stage5 stage6 stage7 stage8 stage9 stage10 stage11 stage_bootloader_crt0_build
	@echo ""
	@echo "✅ =============================================="
	@echo "✅  ASAP Bootloader-CRT0架构编译成功！"
	@echo "✅ =============================================="
	@echo "   最终固件: $(BOOTLOADER_OUT)"
	@ls -lh $(BOOTLOADER_OUT)
	@echo ""

# 编译并链接Bootloader-CRT0版本
stage_bootloader_crt0_build: $(BOOTLOADER_OUT)
$(BOOTLOADER_OUT): $(ASM_INSTRUMENTED) $(BOOTLOADER_CRT0_S) $(RESTORE_O) $(FRAM_SYMBOLS_LD)
	@echo ""
	@echo "[Bootloader-CRT0] 编译包含C初始化的自定义Bootloader"
	@echo "  输入: $(BOOTLOADER_CRT0_S)（Bootloader入口）"
	@echo "  输入: $(ASM_INSTRUMENTED)（已插桩的main）"
	@echo ""
	@echo "  阶段1: 编译Bootloader"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(BOOTLOADER_CRT0_S) -o $(BOOTLOADER_CRT0_O)
	
	@echo "  阶段2: 编译主程序（不插入恢复检查，由bootloader处理）"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(ASM_INSTRUMENTED) -o $(MAIN_O)
	
	@echo "  阶段3: 初步链接（使用自定义Bootloader linker script）"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -nostartfiles \
		-T $(BOOTLOADER_LD) \
		-Wl,--just-symbols=$(FRAM_SYMBOLS_LD) \
		-o $(BOOTLOADER_OUT) \
		$(BOOTLOADER_CRT0_O) \
		$(MAIN_O) \
		$(RESTORE_O) \
		-lgcc
	
	@echo "  阶段4: 从最终固件提取正确的PC映射"
	python3 $(STAGE7) $(BOOTLOADER_OUT) \
		--output $(WID_PC_MAP) \
		--objdump $(OBJDUMP)
	
	@echo "  阶段5: 重新生成恢复逻辑（使用正确PC）"
	python3 $(STAGE11) \
		--pc-ranges $(PC_RANGES) \
		--wid-pc-map $(WID_PC_MAP) \
		--fram-slots $(FRAM_SLOTS) \
		--function-info $(FUNC_INFO) \
		--output $(RESTORE_ASM) \
		--format asm
	
	@echo "  阶段6: 重新编译恢复逻辑"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -c $(RESTORE_ASM) -o $(RESTORE_O)
	
	@echo "  阶段7: 最终链接（使用正确的PC映射）"
	$(COMPILER) -mmcu=$(MCU) $(CFLAGS) -nostartfiles \
		-T $(BOOTLOADER_LD) \
		-Wl,--just-symbols=$(FRAM_SYMBOLS_LD) \
		-o $(BOOTLOADER_OUT) \
		$(BOOTLOADER_CRT0_O) \
		$(MAIN_O) \
		$(RESTORE_O) \
		-lgcc
	
	@echo "  ✓ Bootloader-CRT0架构编译完成"

# ===== 清理 =====
clean:
	@echo "清理构建目录和输出文件..."
	rm -rf $(BUILD_DIR)/*
	rm -f $(OUTPUT)
	rm -f *_asap_*.out firmware_final.out
	@echo "✓ 清理完成"

# ===== 显示配置 =====
show:
	@echo "ASAP编译流程配置："
	@echo "  源文件:       $(SRC)"
	@echo "  编译器:       $(COMPILER)"
	@echo "  目标MCU:      $(MCU)"
	@echo "  编译选项:     $(CFLAGS)"
	@echo "  构建目录:     $(BUILD_DIR)"
	@echo "  最终固件:     $(OUTPUT)"
	@echo ""
	@echo "关键输出文件："
	@echo "  汇编:         $(ASM_SYM)"
	@echo "  插桩汇编:     $(ASM_INSTRUMENTED)"
	@echo "  FRAM槽位:     $(FRAM_SLOTS)"
	@echo "  链接脚本:     $(FRAM_SYMBOLS_LD)"
	@echo "  恢复逻辑:     $(RESTORE_ASM)"
	@echo ""
	@echo "13个编译阶段："
	@echo "  Stage 1:  C源码 → 汇编"
	@echo "  Stage 2:  分析函数信息"
	@echo "  Stage 3:  识别关键写（排除输出）"
	@echo "  Stage 4:  分配FRAM槽位（按地址）"
	@echo "  Stage 5:  插桩备份逻辑"
	@echo "  Stage 6:  编译临时固件"
	@echo "  Stage 7:  提取WID→PC映射"
	@echo "  Stage 8:  分析读写操作"
	@echo "  Stage 9:  生命周期分析（基于地址）"
	@echo "  Stage 10: 合并PC范围"
	@echo "  Stage 11: 生成恢复逻辑（表驱动）"
	@echo "  Stage 12: 编译恢复逻辑和Bootloader"
	@echo "  Stage 13: 最终链接生成.out"

# ===== 帮助 =====
help:
	@echo "ASAP完整编译流程 - 使用帮助"
	@echo ""
	@echo "用法:"
	@echo "  make              - 执行完整的13阶段编译流程"
	@echo "  make stageN       - 执行到第N阶段（1-13）"
	@echo "  make clean        - 清理构建目录"
	@echo "  make show         - 显示配置信息"
	@echo "  make help         - 显示此帮助"
	@echo ""
	@echo "配置变量（可通过命令行覆盖）:"
	@echo "  SRC=<文件>        - 指定C源文件（默认: $(SRC)）"
	@echo "  MCU=<型号>        - 指定MCU型号（默认: $(MCU)）"
	@echo "  CFLAGS=<选项>     - 指定编译选项（默认: $(CFLAGS)）"
	@echo "  OUTPUT=<文件>     - 指定输出文件名（默认: $(OUTPUT)）"
	@echo ""
	@echo "示例:"
	@echo "  make SRC=Test/test.c"
	@echo "  make SRC=Benchmarks/bc/bc_clean.c CFLAGS=\"-O2 -g\""
	@echo "  make clean && make"
	@echo ""
	@echo "断电模拟（用于测试恢复逻辑）:"
	@echo "  make pf_test          - 编译带断电模拟的方案1"
	@echo "  make bootloader_pf    - 编译带断电模拟的方案2"
	@echo ""
	@echo "核心特性:"
	@echo "  ✅ 按地址分配FRAM（一个地址一个槽位）"
	@echo "  ✅ 覆盖写同一槽位（同一地址多次写入）"
	@echo "  ✅ 表驱动恢复逻辑（高效PC范围查找）"
	@echo "  ✅ 直接PC保存（MOV R0, &ASAP_PC_SAVE）"
	@echo "  ✅ 正确的生命周期定义（写→读/下次写/函数结束）"
	@echo "  ✅ 断电模拟测试（基于ImmortalThreads机制）"
	@echo ""

# ===== 断电模拟测试目标 =====
.PHONY: pf_test bootloader_pf

# 方案1：GCC CRT0 + 断电模拟
pf_test:
	@echo ""
	@echo "╔════════════════════════════════════════════╗"
	@echo "║  编译方案1 + 断电模拟测试                 ║"
	@echo "╚════════════════════════════════════════════╝"
	$(MAKE) clean
	$(MAKE) PF_SIMULATION=1
	msp430-elf-objcopy -O ihex firmware_final.out firmware_PF_TEST_METHOD1.hex
	@echo ""
	@echo "✅ 已生成: firmware_PF_TEST_METHOD1.hex"
	@echo "   特性: GCC CRT0 + main插桩 + 定时器断电"
	@echo ""
	@echo "预期行为:"
	@echo "  1. 正常启动: MAIN_V2 → [PF-SIM-ON] → INIT 0"
	@echo "  2. 断电模拟: 程序自动重启（每30-150ms）"
	@echo "  3. 断电恢复: 跳过MAIN_V2，输出 PF#N（断电次数）"
	@echo "  4. 继续执行: 从断点恢复，输出中间状态（F3/F5等）"
	@echo ""

# 方案2：Bootloader-CRT0 + 断电模拟
bootloader_pf:
	@echo ""
	@echo "╔════════════════════════════════════════════╗"
	@echo "║  编译方案2 + 断电模拟测试                 ║"
	@echo "╚════════════════════════════════════════════╝"
	$(MAKE) clean
	$(MAKE) bootloader PF_SIMULATION=1
	msp430-elf-objcopy -O ihex firmware_bootloader_crt0.out firmware_PF_TEST_METHOD2.hex
	@echo ""
	@echo "✅ 已生成: firmware_PF_TEST_METHOD2.hex"
	@echo "   特性: 自定义Bootloader + 定时器断电"
	@echo ""
	@echo "预期行为:"
	@echo "  1. 正常启动: MAIN_V2 → [PF-SIM-ON] → INIT 0"
	@echo "  2. 断电模拟: 程序自动重启（每30-150ms）"
	@echo "  3. 断电恢复: 跳过MAIN_V2，输出 PF#N（断电次数）"
	@echo "  4. 继续执行: 从断点恢复，输出中间状态（F3/F5等）"
	@echo ""
