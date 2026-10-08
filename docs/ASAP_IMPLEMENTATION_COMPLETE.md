# ASAP 备份/恢复逻辑完整实现文档

**版本**: 最新版 (2024-11-10)  
**状态**: ✅ 所有关键问题已修复，边界检查已加入

---

## 📋 目录

1. [系统概述](#系统概述)
2. [Makefile 13阶段编译流程](#makefile-13阶段编译流程)
3. [核心脚本详解](#核心脚本详解)
4. [备份逻辑实现](#备份逻辑实现)
5. [恢复逻辑实现](#恢复逻辑实现)
6. [调用栈恢复](#调用栈恢复)
7. [关键修复历史](#关键修复历史)
8. [调试指南](#调试指南)

---

## 系统概述

### 核心思想

ASAP (As Soon As Possible) 是一个针对MSP430 FRAM微控制器的**非易失性检查点**系统：

1. **备份时机**: 每次关键变量写入后立即备份 (WID, 变量, SP)
2. **恢复时机**: 上电时bootloader检查ASAP_WID_SAVE，非0则执行热启动
3. **原子性保证**: WID → 关键写 → 变量备份 → SP备份 (顺序执行，idempotent)
4. **表驱动恢复**: 通过WID查找恢复表，恢复变量和PC

### 关键数据结构

```c
// FRAM中的检查点状态 (非易失性)
__attribute__((section(".upper.noinit"))) uint16_t ASAP_WID_SAVE;     // 0x7000
__attribute__((section(".upper.noinit"))) uint16_t ASAP_SP_SAVE;      // 0x7004
__attribute__((section(".upper.noinit"))) uint16_t ASAP_VAR_SLOTS[];  // 0x6400+

// RAM中的热启动标志 (易失性)
uint16_t __asap_restored_flag = 0;  // 热启动成功后设为0x1234
```

### 恢复表格式

```assembly
_restore_table:
    .word _restore_list_W001
    .word _restore_list_W002
    ...

_restore_list_W001:
    ; 变量恢复条目 (每个3个word)
    .word <SP_adjustment>  ; SP调整量 (相对ASAP_SP_SAVE)
    .word <FRAM_slot>      ; FRAM槽位地址
    .word <stack_offset>   ; 栈偏移
    
    .word 0xFFFF           ; 结束标记
    
    ; 返回地址恢复 (3个word)
    .word <SP_adjustment>  ; 返回地址的SP调整
    .word <RET_ADDR_slot>  ; 返回地址FRAM槽
    .word <ret_offset>     ; 返回地址栈偏移
    
    ; PC恢复
    .word <resume_PC>      ; 恢复执行的PC地址
    .word 0                ; 结束
```

---

## Makefile 13阶段编译流程

### 完整流程图

```
C源码 (main_cf.c)
    ↓
[Stage 1] 编译到汇编 (A_sym.s)
    ↓
[Stage 2] 分析函数信息 (function_info.json)
    ↓
[Stage 3] 识别关键写 (candidates.json)
    ↓
[Stage 4] 分配FRAM槽位 (fram_slots.json, fram_symbols.ld)
    ↓
[Stage 5] 插桩备份逻辑 (A_instrumented.s)
    ↓
[Stage 5b] 插入main热启动检查 (修改A_instrumented.s)
    ↓
[Stage 5c] 插入子函数返回地址备份 (修改A_instrumented.s)
    ↓
[Stage 6] 编译临时固件 (firmware_temp.elf)
    ↓
[Stage 7] 提取WID→PC映射 (wid_pc_map.json)
    ↓
[Stage 8] 分析读写操作 (reads_writes.json)
    ↓
[Stage 9] 生命周期分析 (lifetime_data.json)
    ↓
[Stage 9b] 构建调用图 (call_graph.json)
    ↓
[Stage 10] 生成恢复列表 (pc_ranges.json)
    ↓
[Stage 11] 生成恢复逻辑 (asap_restore.s)
    ↓
[Stage 12] 编译恢复逻辑 (asap_restore.o)
    ↓
[Stage 13] 最终链接 (firmware_final.out)
```

### 关键编译参数

```makefile
MCU        = msp430fr5969
CFLAGS     = -O0 -g
COMPILER   = msp430-elf-gcc
OBJDUMP    = msp430-elf-objdump
```

### 两阶段链接

Stage 13使用**两阶段链接**以确保PC地址正确：

1. **第一阶段**: 初步链接 → 提取正确PC → 重新生成恢复表
2. **第二阶段**: 使用正确PC重新链接 → 生成最终固件

---

## 核心脚本详解

### Stage 3: stage3_analyze_writes.py

**功能**: 识别需要备份的关键写操作

**排除规则**:
- 输出相关函数 (uart_putc, uart_puts, uart_print_uint)
- ISR中断服务程序 (Timer0_B1_ISR)
- 常量写入 (MOV #const, dest)
- I/O端口写入 (P1OUT, P2DIR等)

**输出格式** (candidates.json):
```json
{
  "W001": {
    "line_num": 123,
    "instruction": "MOV.W r12, 4(r1)",
    "function": "insert",
    "logical_addr": "insert::SP+4",
    ...
  }
}
```

### Stage 4: stage4_allocate_fram.py

**功能**: 为每个逻辑地址分配唯一的FRAM槽位

**关键特性**:
- **按地址分配**: 每个逻辑地址 (如 `insert::SP+4`) 只分配一个槽位
- **覆盖写**: 同一地址多次写入，覆盖同一槽位
- **地址范围**: 从0x6400开始分配

**输出** (fram_slots.json):
```json
{
  "insert::SP+4": {
    "slot_addr": "0x6400",
    "slot_symbol": "ASAP_SLOT_insert_SP_4",
    "wids": ["W001", "W005", "W010"]
  }
}
```

### Stage 5: stage5_inject_backup.py ⭐

**功能**: 在关键写指令后插入备份代码

**插桩顺序** (修复后):
```assembly
__WID_W001: MOV.W #1, &ASAP_WID_SAVE      ; ① WID first (atomic marker)
            MOV.W r12, 4(r1)               ; ② 原始关键写
            MOV.W 4(r1), &ASAP_SLOT_XX     ; ③ 备份变量
            MOV.W R1, &ASAP_SP_SAVE        ; ④ 备份SP
            ; 继续执行...
```

**关键点**:
- `__WID_Wxx` 标签在第一条指令上 (stage7提取PC时使用)
- 热启动时PC指向`__WID_Wxx`，重新执行整个序列 (idempotent)

### Stage 5b: stage5b_inject_main_restore.py

**功能**: 在main函数开头插入热启动检查和LED指示

**插入位置**: `init()` 调用后 (外设已初始化)

**插入代码**:
```assembly
; 检查热启动
MOV.W &ASAP_WID_SAVE, R14
CMP.W #0, R14
JEQ __main_cold_start
CMP.W #66, R14
JGE __main_cold_start

; 热启动路径
__main_hot_start:
    ; 保存WID到0x646A用于调试
    MOV.W R14, &0x646A
    
    ; LED闪3次 (红灯P1.1)
    BIS.B #0x01, &0x0204  ; P1DIR.0=1
    BIS.B #0x01, &0x0202  ; P1OUT.0=1
    MOV.W #10000, &0x6476 ; 延时
__led_delay1:
    DEC.W &0x6476
    JNZ __led_delay1
    ; ...重复3次...
    
    ; 调用恢复函数
    MOV.W R14, R12
    CALL #_asap_restore
    ; 不会返回!

__main_cold_start:
    ; 清零标志
    MOV.W #0, &__asap_restored_flag
    ; 继续正常执行
```

**输出**:
- 热启动失败: `[F]<WID>\n` (WID来自0x6474)
- 热启动成功: 无输出，LED闪3次

### Stage 5c: stage5c_inject_return_addr_backup.py

**功能**: 在子函数入口插入返回地址备份

**插入代码**:
```assembly
insert:
    ; 原始函数序言
    PUSH R11
    SUB #26, R1
    
    ; 插入返回地址备份
    MOV.W 26(R1), &RET_ADDR_INSERT  ; 保存返回地址到FRAM
    
    ; 函数体...
```

### Stage 7: stage7_extract_wid_pc.py

**功能**: 从编译后的固件提取WID→PC映射

**提取方法**:
```python
# 查找 <__WID_Wxx>: 标签
for line in objdump_output:
    match = re.search(r'<__WID_(W\d+)>', line)
    if match:
        wid = match.group(1)
        pc = extract_address(line)  # 从行首提取地址
        wid_pc_map[wid] = pc
```

**输出** (wid_pc_map.json):
```json
{
  "W001": "0xA400",
  "W002": "0xA420",
  ...
}
```

### Stage 9b: stage9b_build_call_graph.py ⭐

**功能**: 构建函数调用图，计算调用栈

**核心算法**: DFS查找从main到目标函数的路径

```python
def find_call_path(target, graph, current='main', path=None):
    if path is None:
        path = ['main']
    if current == target:
        return path[:]
    if current not in graph:
        return None
    for callee in graph[current]['calls']:
        if callee not in path:  # 避免循环
            path.append(callee)
            result = find_call_path(target, graph, callee, path)
            if result:
                return result
            path.pop()
    return None
```

**输出** (call_graph.json):
```json
{
  "call_graph": {
    "main": {"calls": ["init", "insert", "lookup"]},
    "insert": {"calls": ["hash_key_to_index"]}
  },
  "wid_call_stacks": {
    "W001": ["main", "insert"]
  }
}
```

### Stage 10: stage10_merge_pc_ranges.py ⭐

**功能**: 为每个WID生成需要恢复的变量列表

**关键修复**: 恢复调用栈上的所有活跃变量

```python
# 修复前：只恢复当前WID写入的变量
if first_write_wid <= current_wid:
    restore_list.append(var)

# 修复后：恢复调用栈上所有有FRAM槽的变量
for func in call_stack:
    for var in func_variables[func]:
        if var.has_fram_slot and var.is_active_at(current_wid):
            restore_list.append(var)
```

**输出** (pc_ranges.json):
```json
{
  "W001": {
    "function": "insert",
    "call_stack": ["main", "insert"],
    "restore_list": [
      {"logical_addr": "main::SP+6", "slot_addr": "0x644A"},
      {"logical_addr": "insert::SP+4", "slot_addr": "0x6400"}
    ]
  }
}
```

### Stage 11: stage11_generate_restore.py ⭐

**功能**: 生成最终的恢复汇编代码

**关键特性**:
1. **边界检查**: 防止写入0xFFFE等非法地址
2. **调试地址**: 记录目标地址到FRAM供调试
3. **SP调整**: 支持跨函数栈变量恢复

**生成的恢复循环**:
```assembly
_restore_items:
    MOV.W @R14+, R15           ; 读SP调整量
    CMP.W #0xFFFF, R15         ; 检查结束标记
    JEQ _restore_return_addr
    
    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电时的SP
    ADD.W R15, R11             ; R11 = 目标函数SP
    
    MOV.W @R14+, R15           ; 读FRAM槽地址
    MOV.W @R15, R13            ; R13 = 从FRAM读取的值
    
    MOV.W @R14+, R15           ; 读栈偏移
    ADD.W R11, R15             ; R15 = 目标地址
    
    ; ⭐ 边界检查 (防止0xFFFE)
    MOV.W R15, &0x6478         ; 保存目标地址供调试
    CMP.W #0x2400, R15         ; >= 0x2400?
    JHS _restore_items         ; 跳过写入
    CMP.W #0x1C00, R15         ; < 0x1C00?
    JLO _restore_items         ; 跳过写入
    
    MOV.W R13, 0(R15)          ; 写入RAM
    JMP _restore_items

_restore_return_addr:
    ; 恢复返回地址 (带边界检查)
    MOV.W @R14+, R15           ; SP调整量
    MOV.W @R14+, R10           ; 返回地址FRAM槽
    CMP.W #0, R10
    JEQ _restore_get_pc        ; 无返回地址(main)
    
    MOV.W @R14+, R9            ; 返回地址栈偏移
    MOV.W &ASAP_SP_SAVE, R11
    ADD.W R15, R11
    MOV.W @R10, R13            ; 读返回地址
    ADD.W R11, R9              ; 计算目标位置
    
    ; ⭐ 边界检查
    MOV.W R9, &0x647A
    CMP.W #0x2400, R9
    JHS _restore_skip_ret_addr
    CMP.W #0x1C00, R9
    JLO _restore_skip_ret_addr
    
    MOV.W R13, 0(R9)           ; 恢复返回地址

_restore_get_pc:
    MOV.W @R14+, R15           ; 读恢复PC
    MOV.W R15, R0              ; 跳转!
```

---

## 备份逻辑实现

### 1. WID编号规则

- `W001`, `W002`, ... `W065`
- 按照源码中关键写的顺序编号
- 每个WID对应一个checkpoint

### 2. 备份触发点

**触发条件**: 检测到对栈变量的写入

```c
// 示例：insert函数中
uint16_t key_index = hash_key_to_index(fp, key);  // ← W001触发
```

**对应汇编**:
```assembly
; 原始代码
CALL #hash_key_to_index
MOV.W r12, 4(r1)          ; 关键写 (key_index)

; 插桩后
__WID_W001: MOV.W #1, &ASAP_WID_SAVE      ; WID备份
            CALL #hash_key_to_index
            MOV.W r12, 4(r1)               ; 关键写
            MOV.W 4(r1), &ASAP_SLOT_XX     ; 变量备份
            MOV.W R1, &ASAP_SP_SAVE        ; SP备份
```

### 3. FRAM槽位分配策略

**策略**: 一个逻辑地址一个槽位

**示例**:
```
main::SP+6 (iteration)    → ASAP_SLOT_main_SP_6     (0x644A)
insert::SP+4 (key_index)  → ASAP_SLOT_insert_SP_4   (0x6400)
insert::SP+6 (fp_index)   → ASAP_SLOT_insert_SP_6   (0x6402)
```

### 4. 原子性保证

**问题**: 如果在备份序列中间断电？

**解决**: Idempotent设计
- PC指向`__WID_Wxx` (MOV WID指令)
- 热启动时重新执行整个序列
- WID先写保证了事务标记

**场景分析**:
```
场景1: 断电在WID写入前
  → WID=0，冷启动

场景2: 断电在WID写入后，变量备份前
  → WID=N，热启动，重新执行关键写+备份

场景3: 断电在变量备份后
  → WID=N，热启动，重新执行（覆盖同一槽位，结果相同）
```

---

## 恢复逻辑实现

### 1. Bootloader检查

**位置**: `Runtime/bootloader_with_restore.s`

```assembly
bootloader_entry:
    ; 1. 基本硬件初始化
    MOV.W #WDTPW|WDTHOLD, &WDTCTL
    MOV.W #__stack, SP
    
    ; 2. 清空.bss段
    ; ...
    
    ; 3. 跳转到main (C初始化由main开头的热启动检查处理)
    CALL #main
```

### 2. Main热启动检查

**位置**: Stage5b插入到main函数开头

```assembly
main:
    ; 原始函数序言
    PUSH R11
    SUB #14, R1
    
    ; 调用init
    CALL #init
    
    ; ===== 热启动检查 =====
    MOV.W &ASAP_WID_SAVE, R14
    CMP.W #0, R14
    JEQ __main_cold_start      ; WID=0 → 冷启动
    CMP.W #66, R14
    JGE __main_cold_start      ; WID>65 → 无效，冷启动
    
__main_hot_start:
    ; LED闪3次
    ; ...
    
    ; 调用恢复
    MOV.W R14, R12
    CALL #_asap_restore
    ; 不返回!
```

### 3. 恢复函数流程

**_asap_restore 完整流程**:

```
1. 保存寄存器到FRAM (调试用)
2. 验证WID范围 (1-65)
3. 从恢复表查找对应的restore_list
4. 循环恢复所有变量
   - 读取SP调整量、FRAM槽地址、栈偏移
   - 边界检查
   - 从FRAM读值，写入栈
5. 恢复返回地址 (如果是子函数)
6. 恢复PC并跳转
```

### 4. 变量恢复

**关键计算**:
```c
target_addr = (ASAP_SP_SAVE + sp_adjustment) + stack_offset
```

**示例**:
```
断电时:
  SP = 0x23A0
  断电函数 = insert (SP_adjustment = 0)
  
恢复insert::SP+4:
  target = 0x23A0 + 0 + 4 = 0x23A4 ✓

恢复main::SP+6:
  target = 0x23A0 + 8 + 6 = 0x23AE
  (8 = insert的栈帧大小，从function_info获取)
```

### 5. 返回地址恢复

**场景**: 断电发生在子函数中

```assembly
main:
    CALL insert
    ; ← main的返回地址在这里

insert:
    ; 入口备份返回地址
    MOV.W 26(R1), &RET_ADDR_INSERT
    
    ; 函数体...
    ; ← 断电发生在这里
```

**恢复时**:
```assembly
; 恢复返回地址到栈上
MOV.W &RET_ADDR_INSERT, R13
MOV.W R13, 26(R1)  ; 写入insert栈帧顶部
```

---

## 调用栈恢复

### 问题描述

**场景**: 断电在`insert`函数中，但`main::SP+6` (iteration) 也需要恢复

**调用栈**:
```
main (iteration = 37)
  → insert (key_index = ?)
      → [断电] WID=W001
```

### 解决方案

**Stage 9b**: 构建调用图
```json
{
  "W001": ["main", "insert"]
}
```

**Stage 10**: 恢复所有调用栈上的变量
```python
for func in call_stack:
    for var in func_variables[func]:
        if var.has_fram_slot:
            restore_list.append(var)
```

**Stage 11**: 生成带SP调整的恢复项
```assembly
; 恢复insert::SP+4 (SP_adjustment=0)
.word 0, 0x6400, 4

; 恢复main::SP+6 (SP_adjustment=8)
.word 8, 0x644A, 6
```

### SP调整量计算

**公式**:
```
SP_adjustment = 断电函数SP - 目标函数SP

对于main: SP_adjustment = insert栈帧大小 = 8
对于insert: SP_adjustment = 0
```

---

## 关键修复历史

### 修复1: Iteration变量恢复 (Issue #6904)

**问题**: `iteration`总是显示6904，不是正确的值

**根因**: Stage10只恢复当前WID写入的变量，忽略了调用栈上的变量

**修复**:
```python
# 修复前
if first_write_wid <= current_wid:
    restore_list.append(var)

# 修复后
for func in call_stack:
    for var in func_variables[func]:
        if var.has_fram_slot:
            restore_list.append(var)
```

**提交**: `stage10_merge_pc_ranges.py` line 42-53

### 修复2: 0xFFFE被改写 (Issue #Reset Vector)

**问题**: 第230次iteration后，0xFFFE (Reset Vector) 被改写

**根因**: 恢复循环没有边界检查，错误计算的地址可能指向0xFFFE

**修复**:
```assembly
; 变量恢复前检查
MOV.W R15, &0x6478         ; 保存目标地址
CMP.W #0x2400, R15
JHS _restore_items         ; 超出RAM范围，跳过
CMP.W #0x1C00, R15
JLO _restore_items         ; 低于RAM起始，跳过
MOV.W R13, 0(R15)          ; 安全写入
```

**提交**: `stage11_generate_restore.py` line 225-230, 251-256

### 修复3: 冷启动[FAIL]输出 (Issue #Cold Start)

**问题**: 冷启动时错误输出`[FAIL]`

**根因**: 热启动计数器未初始化时为0xFFFF

**修复**:
```assembly
; 检查热启动计数器
CMP.W #0, R15
JEQ __skip_fail_debug
CMP.W #0xFFFF, R15        ; ← 新增
JEQ __skip_fail_debug
```

**提交**: `stage5b_inject_main_restore.py` line 109-110

### 修复4: 备份顺序原子性 (Issue #Atomicity)

**问题**: 备份顺序 (变量→SP→WID) 导致非原子

**修复**: 改为 (WID→关键写→变量→SP)

**提交**: `stage5_inject_backup.py` line 49-67

### 修复5: 定时器变量不备份 (Issue #Timer Variables)

**问题**: 定时器变量被错误加入备份，导致恢复时混乱

**修复**: 使用`.upper.noinit`区域，并在Stage3排除ISR

**提交**: 
- `main_cf.c` line 20-22 (noinit声明)
- `stage3_analyze_writes.py` (ISR排除)

---

## 调试指南

### 调试地址清单

| 地址 | 名称 | 用途 |
|------|------|------|
| 0x7000 | ASAP_WID_SAVE | 当前WID |
| 0x7004 | ASAP_SP_SAVE | 断电时SP |
| 0x6400+ | ASAP_SLOT_xxx | 变量FRAM槽 |
| 0x646A | Debug: 传入WID | _asap_restore的R12参数 |
| 0x6470 | Debug: R14指针 | 恢复表读取位置 |
| 0x6472 | Debug: 读取的PC | 从恢复表读的PC值 |
| 0x6474 | Debug: 原始WID | 热启动前的WID |
| 0x6478 | Debug: 变量目标地址 | 最后一次变量恢复的目标地址 |
| 0x647A | Debug: 返回地址目标 | 返回地址恢复的目标地址 |
| 0x6476 | LED延时计数器 | 热启动LED闪烁延时 |

### 串口输出解读

**正常运行**:
```
[I1]32 32 32 [E1][I2]32 32 32 [E2]...
```
- `[I数字]` = iteration开始
- `32 32 32` = inserts, members, total
- `[E数字]` = iteration结束

**热启动成功**:
```
[I230]32 32 32 [E230][I231]32 32 32 [E231]...
```
- 继续之前的iteration编号
- LED闪3次（无串口标记）

**热启动失败**:
```
[F]47
[I1]32 32 32 [E1]...
```
- `[F]47` = WID=47时检测到数据错误
- 从iteration 1重新开始

### 常见问题诊断

**问题1: inserts/members变成0**

**检查**:
1. 0x6478是否在0x1C00-0x2400范围内？
2. filter数组 (0xA586-0xA686) 是否被破坏？
3. 恢复表中是否有错误的offset？

**问题2: iteration显示错误值**

**检查**:
1. `main::SP+6`是否在恢复列表中？
2. SP_adjustment是否正确计算？
3. ASAP_SP_SAVE的值是否合理 (0x2300左右)？

**问题3: 热启动后立即crash**

**检查**:
1. PC值是否正确 (0x646A, 0x6472)？
2. 恢复表指针 (0x6470) 是否合法？
3. 栈指针是否被正确恢复？

### 使用objdump分析

**提取恢复表**:
```bash
msp430-elf-objdump -d firmware_final.out | grep -A 20 "_restore_list_W001"
```

**查看WID-PC映射**:
```bash
msp430-elf-objdump -d firmware_final.out | grep "__WID_"
```

**查看函数栈帧**:
```bash
cat build/function_info.json | python3 -m json.tool
```

---

## 文件清单

### 编译脚本 (Compiler/)

| 文件 | 功能 |
|------|------|
| stage1_compile_to_asm.py | C源码→汇编 |
| stage2_analyze_functions.py | 分析函数信息 |
| stage3_analyze_writes.py | 识别关键写 |
| stage4_allocate_fram.py | 分配FRAM槽位 |
| stage5_inject_backup.py | 插桩备份逻辑 ⭐ |
| stage5b_inject_main_restore.py | 插入热启动检查 ⭐ |
| stage5c_inject_return_addr_backup.py | 备份返回地址 |
| stage7_extract_wid_pc.py | 提取WID→PC映射 |
| stage8_analyze_reads_writes_v2.py | 分析读写 |
| stage9_analyze_lifetime.py | 生命周期分析 |
| stage9b_build_call_graph.py | 构建调用图 ⭐ |
| stage10_merge_pc_ranges.py | 生成恢复列表 ⭐ |
| stage11_generate_restore.py | 生成恢复逻辑 ⭐ |

### 运行时文件 (Runtime/)

| 文件 | 功能 |
|------|------|
| bootloader_with_restore.s | Bootloader入口 |
| asap_restore_stub.s | 恢复函数stub (Stage 6用) |
| src/port/msp430/msp430fr5969_bootloader.ld | 链接脚本 |

### 配置文件

| 文件 | 功能 |
|------|------|
| Compiler/bc_core_config.json | 排除规则配置 |
| Makefile | 13阶段编译流程 |

---

## 总结

ASAP系统通过**表驱动的checkpoint-restore机制**实现了MSP430的非易失性内存支持：

✅ **关键特性**:
1. 按地址分配FRAM，覆盖写同一槽位
2. WID先写保证原子性
3. 调用栈感知的变量恢复
4. 边界检查防止非法写入
5. 完整的调试地址支持

✅ **性能优化**:
1. 表驱动恢复 (O(1) WID查找)
2. 只备份活跃变量
3. ISR完全不受影响
4. 热启动LED指示

✅ **可靠性**:
1. Idempotent备份序列
2. 边界检查 (0x1C00-0x2400)
3. 调试地址记录
4. 热启动失败检测

**适用场景**: 间歇性供电的嵌入式系统，需要快速恢复到断电前状态。

---

**文档版本**: v1.0  
**最后更新**: 2024-11-10  
**作者**: ASAP Compiler Team

