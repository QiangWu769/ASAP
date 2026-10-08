# 恢复表去重优化详解

## 问题背景

在编译 CF (Cuckoo Filter) 基准测试时，遇到了代码空间溢出问题：
- 91 个 WID
- 原版本生成了 91 份完整的恢复列表
- 恢复逻辑代码：13,421 行汇编
- 编译结果：**代码空间溢出，链接失败**

## 问题分析

通过分析发现，**恢复表存在大量重复内容**：

```
总 WID 数: 91
唯一恢复列表数: 8
重复率: 91.2%
```

具体分布：
- 48 个 WID (W044-W091) 共享同一个恢复列表（39项）
- 22 个 WID (W016-W037) 共享同一个恢复列表（53项）
- 9 个 WID (W001-W009) 共享同一个恢复列表（59项）
- ...

## 去重策略

### 原版本结构

```assembly
; 每个 WID 都有完整的恢复列表
_restore_list_W001:
    .word 0, __SLOT_djb_hash_SP_2, 2
    .word 0, __SLOT_djb_hash_SP_0, 0
    ...（59项）
    .word 0xFFFF  ; 返回地址标记
    .word 0x927A  ; W001 的 PC

_restore_list_W002:
    .word 0, __SLOT_djb_hash_SP_2, 2
    .word 0, __SLOT_djb_hash_SP_0, 0
    ...（59项，与W001完全相同！）
    .word 0xFFFF  ; 返回地址标记
    .word 0x928E  ; W002 的 PC (不同)

_restore_table:
    .word _restore_list_W001
    .word _restore_list_W002
    ...
```

**问题**：W001 和 W002 的恢复列表除了 PC 不同外，其余内容完全相同，造成大量重复。

### 去重版本结构

```assembly
; 唯一的恢复列表（去重后）
_unique_restore_list_1:
    .word 0, __SLOT_djb_hash_SP_2, 2
    .word 0, __SLOT_djb_hash_SP_0, 0
    ...（59项）
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; PC 占位符（在跳转表中指定）

; 跳转表：每个 WID 包含 [恢复列表指针, PC]
_restore_table:
    .word _unique_restore_list_1, 0x927A  ; W001 → 列表1, PC
    .word _unique_restore_list_1, 0x928E  ; W002 → 列表1, PC
    .word _unique_restore_list_1, 0x92A2  ; W003 → 列表1, PC
    ...
```

**优化**：相同的恢复列表只生成一次，PC 在跳转表中单独存储。

## 正确性验证

### 关键问题

即使恢复列表相同，每个 WID 的 PC、SP、返回地址都不同，去重后还正确吗？

### 答案：正确！

#### 1. PC（程序计数器）

**原版本**：PC 存储在每个恢复列表的末尾
**去重版本**：PC 存储在跳转表中

恢复流程：
```assembly
; 查跳转表
MOV.W &ASAP_WID_SAVE, R12      ; R12 = WID
DEC.W R12                       ; R12 = WID-1
RLA.W R12                       ; R12 = (WID-1)*2
RLA.W R12                       ; R12 = (WID-1)*4 (每项4字节)
ADD.W #_restore_table, R12      ; R12 = table地址
MOV.W @R12+, R14                ; R14 = 恢复表指针
MOV.W @R12, R15                 ; R15 = 恢复PC (每个WID独立)
MOV.W R15, &ASAP_PC_SAVE        ; 保存PC
```

✅ **结果**：每个 WID 仍然有自己独立的 PC

#### 2. SP（栈指针）

SP 不是静态存储的，而是**运行时从 FRAM 读取**：

```assembly
MOV.W &ASAP_SP_SAVE, R11   ; 读取断电时保存的 SP
```

流程：
1. W001 断电时：备份逻辑保存 SP=0x2380 到 ASAP_SP_SAVE
2. W001 恢复时：从 ASAP_SP_SAVE 读取 SP=0x2380
3. W002 断电时：备份逻辑保存 SP=0x2378 到 ASAP_SP_SAVE（覆盖）
4. W002 恢复时：从 ASAP_SP_SAVE 读取 SP=0x2378

✅ **结果**：每个 WID 恢复时使用的是自己断电时的 SP

#### 3. 返回地址

返回地址也是**运行时从 FRAM 读取**：

```assembly
MOV.W @R10, R13        ; 从 RET_ADDR_DJBHASH 读取返回地址
```

流程：
1. W001 在 djb_hash 中断电：Stage 5c 备份返回地址到 RET_ADDR_DJBHASH
2. W001 恢复时：从 RET_ADDR_DJBHASH 读取返回地址
3. W002 在 djb_hash 中断电：Stage 5c 备份返回地址到 RET_ADDR_DJBHASH（覆盖）
4. W002 恢复时：从 RET_ADDR_DJBHASH 读取返回地址

✅ **结果**：每个 WID 恢复时使用的是自己断电时的返回地址

#### 4. 恢复目标地址

恢复列表存储的是：**需要恢复哪些变量**（逻辑地址）

```assembly
; 恢复 djb_hash::SP+0
MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电时的SP (运行时)
ADD.W R15, R11             ; R11 = 目标函数SP
MOV.W @R14+, R10           ; R10 = FRAM槽位地址
MOV.W @R10, R13            ; R13 = FRAM中的值
MOV.W @R14+, R9            ; R9 = 栈偏移量 (0)
MOV.W R11, R15             ; R15 = 目标函数SP
ADD.W R9, R15              ; R15 = 目标地址 = SP + 0
MOV.W R13, 0(R15)          ; 写入目标地址
```

**关键**：目标地址 = (运行时读取的SP) + 偏移

即使 W001 和 W002 的恢复列表相同（都是 djb_hash::SP+0），由于它们断电时的 SP 不同，实际恢复的内存地址也不同。

✅ **结果**：即使恢复列表相同，由于 SP 不同，实际恢复的内存地址也不同

## 去重条件

```python
def restore_list_to_tuple(restore_list):
    items = []
    for item in restore_list:
        logical_addr = item.get('logical_addr', '')      # djb_hash::SP+0
        slot_addr = item.get('slot_addr', '')             # 0x6400
        redirect_target = item.get('redirect_target', '') # 重定向目标
        items.append((logical_addr, slot_addr, redirect_target))
    return tuple(items)
```

**只比较逻辑地址、FRAM槽位和重定向目标，不比较 PC、SP、返回地址**

这是安全的，因为：
1. PC - 在跳转表中单独存储，每个 WID 都有自己的 PC ✅
2. SP - 运行时从 ASAP_SP_SAVE 读取，每次断电都保存真实 SP ✅  
3. 返回地址 - 运行时从 RET_ADDR_XXX 读取，每次断电都保存 ✅
4. 恢复目标地址 - 由 (运行时SP + 偏移) 动态计算 ✅

## 优化效果

### 代码大小对比

|                     | 原版本(未去重) | 去重优化版本 | 减少      |
|---------------------|---------------|-------------|-----------|
| 恢复逻辑代码行数    | 13,421 行     | 1,606 行    | 88.0% ↓   |
| 最终固件大小        | 编译失败      | 8,422 字节  | 成功编译！ |

### 去重统计

- 总 WID 数: 91 个
- 唯一恢复列表: 8 个
- 去重率: 91.2%

### 恢复列表分布

1. 恢复列表 #8 (39项): 被 48 个 WID 共享 (W044-W091)
2. 恢复列表 #6 (53项): 被 22 个 WID 共享 (W016-W037)
3. 恢复列表 #1 (59项): 被 9 个 WID 共享 (W001-W009)
4. 恢复列表 #7 (45项): 被 6 个 WID 共享 (W038-W043)
5. 恢复列表 #2 (55项): 被 2 个 WID 共享 (W010-W011)
6. 恢复列表 #3 (55项): 被 2 个 WID 共享 (W012-W013)
7. 恢复列表 #4 (54项): 被 1 个 WID 共享 (W014)
8. 恢复列表 #5 (40项): 被 1 个 WID 共享 (W015)

## 实现文件

- **优化前**：`Compiler/stage11_generate_restore.py`
- **优化后**：`Compiler/stage11_generate_restore_dedup.py`
- **编译脚本**：`compile_cf_dedup.sh`

## 使用方法

```bash
# 使用去重优化版本编译
make SRC=Benchmarks/cf/main_cf.c \
     OUTPUT=cf_asap_timer_dedup.out \
     TIMER=1 \
     STAGE11=Compiler/stage11_generate_restore_dedup.py
```

## 结论

✅ 去重优化成功解决了代码空间溢出问题  
✅ 恢复逻辑代码减少了 88%  
✅ CF 基准测试现在可以成功编译了  
✅ 去重逻辑**完全正确**，不影响恢复的正确性

恢复列表只是一个"模板"，告诉恢复逻辑"需要恢复哪些变量，从哪个 FRAM 槽位读取"，而实际的 PC、SP、返回地址都是运行时动态的！


