# 数组索引感知备份 - 使用说明

## 新增脚本

已创建以下4个新脚本，支持数组的索引感知备份/恢复：

1. **stage3_analyze_writes_array.py** - 识别数组写入
2. **stage4_allocate_fram_array.py** - 为数组分配连续FRAM空间
3. **stage5_inject_backup_array.py** - 插入索引感知备份指令
4. **stage11_generate_restore_array.py** - 生成数组恢复逻辑

## 使用方法

### 在Makefile中添加数组支持

修改相关stage，添加 `--enable-array-*` 开关：

```makefile
# Stage 3: 识别关键写（包括数组）
stage3: $(CANDIDATES)
$(CANDIDATES): $(ASM_IDEMPOTENT) $(FUNC_INFO)
    python3 Compiler/stage3_analyze_writes_array.py $(ASM_IDEMPOTENT) \
        --functions $(FUNC_INFO) \
        --config $(BC_CONFIG) \
        --output $(CANDIDATES) \
        --enable-array-detection    # ← 新增

# Stage 4: 分配FRAM（包括数组备份空间）
stage4: $(FRAM_SLOTS) $(FRAM_SYMBOLS_LD)
    python3 Compiler/stage4_allocate_fram_array.py $(CANDIDATES) \
        --output $(FRAM_SLOTS) \
        --linker $(FRAM_SYMBOLS_LD)

# Stage 5: 插桩备份（数组索引感知）
stage5: $(ASM_INSTRUMENTED)
    python3 Compiler/stage5_inject_backup_array.py $(ASM_IDEMPOTENT) \
        --candidates $(CANDIDATES) \
        --fram-slots $(FRAM_SLOTS) \
        --output $(ASM_INSTRUMENTED) \
        --enable-array-backup       # ← 新增

# Stage 11: 生成恢复逻辑（包括数组恢复）
stage11: $(RESTORE_ASM)
    python3 Compiler/stage11_generate_restore_array.py \
        --pc-ranges $(PC_RANGES) \
        --wid-pc-map $(WID_PC_MAP) \
        --fram-slots $(FRAM_SLOTS) \
        --candidates $(CANDIDATES) \
        --output $(RESTORE_ASM)
```

## 工作原理

### 1. 数组检测（Stage 3）

识别特征：
- 地址通过RLAM（左移）计算
- 在循环内（有.L标签）
- 读取栈变量作为索引

生成的candidates.json会包含：
```json
{
  "W_001": {
    "type": "array",
    "array_info": {
      "is_array": true,
      "index_location": "2010(R1)",
      "array_base": "vec",
      "loop_label": ".L4"
    }
  }
}
```

### 2. 备份插桩（Stage 5）

对于数组写入，生成索引感知备份：
```asm
; 原始写入
MOV.W  2010(R1), @R12        ; vec[i] = i

; 索引感知备份（4条指令）
MOV.W  2010(R1), R14         ; R14 = i
RLAM.W #1, R14               ; R14 = i*2
ADD.W  &__backup_vec_start, R14  ; R14 = backup_base + i*2
MOV.W  @R12, @R14            ; backup_vec[i] = vec[i]
```

### 3. 数组恢复（Stage 11）

生成循环恢复代码：
```asm
.L_restore_vec:
    MOV.W  R15, R12
    RLAM.W #1, R12
    MOV.W  #__backup_vec_start, R13
    ADD.W  R12, R13
    MOV.W  #1002, R14
    ADD.W  R1, R14
    ADD.W  R12, R14
    MOV.W  @R13, @R14            ; vec[idx] = backup_vec[idx]
    ADD.W  #1, R15
    CMP.W  #500, R15
    JNE    .L_restore_vec
```

## 链接脚本

确保 fram_symbols.ld 包含数组备份基址：
```ld
/* 数组备份区 */
PROVIDE(__backup_vec_start = 0x6800);
PROVIDE(__backup_out_start = 0x6B00);
```

## 测试

使用 conv benchmark 测试：
```bash
make clean
make SRC=Benchmarks/conv/main_conv_plain.c
```

检查生成的汇编：
```bash
cat build/A_instrumented.s | grep "ASAP数组备份" -A 5
```

## 注意事项

1. **C代码需要幂等化**：卷积循环需要使用临时变量
2. **栈空间需求**：局部数组版本需要约4KB栈空间
3. **FRAM空间**：每个数组需要相同大小的备份空间（如vec[500]需要1000字节）
4. **兼容性**：新脚本不影响现有标量备份逻辑，可以共存





