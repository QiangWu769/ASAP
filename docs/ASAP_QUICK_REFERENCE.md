# ASAP 快速参考

## 编译命令

```bash
# 完整编译
cd /Users/wyf/Desktop/ASAP_right/backups/complete_backup_before_no_sp_20251105_204648
make clean && make

# 生成hex文件
msp430-elf-objcopy -O ihex firmware_final.out firmware_final.hex
```

## 串口输出

| 场景 | 输出格式 | 说明 |
|------|----------|------|
| 冷启动 | `[I1]32 32 32 [E1]...` | 从iteration 1开始 |
| 热启动成功 | `[I231]32 32 32 [E231]...` | 继续之前编号，LED闪3次 |
| 热启动失败 | `[F]47[I1]32 32 32 [E1]...` | 输出失败WID，重新开始 |

## 调试地址

| 地址 | 名称 | 查看方法 |
|------|------|----------|
| 0x7000 | ASAP_WID_SAVE | Memory View |
| 0x7004 | ASAP_SP_SAVE | Memory View |
| 0x6478 | 变量恢复目标地址 | Memory View (最新) |
| 0x647A | 返回地址恢复目标 | Memory View (最新) |
| 0xA586 | filter数组起始 | Memory View (业务数据) |

## 关键文件

| 文件 | 用途 |
|------|------|
| `Makefile` | 13阶段编译流程 |
| `build/candidates.json` | 备份候选列表 (WID) |
| `build/fram_slots.json` | FRAM槽位分配 |
| `build/call_graph.json` | 函数调用图 |
| `build/pc_ranges.json` | 恢复列表 (每个WID) |
| `build/asap_restore.s` | 恢复逻辑汇编 |

## 常见问题

### inserts/members变成0

**原因**: filter数组被破坏  
**检查**: 
1. `0x6478`的值是否在`0x1C00-0x2400`范围内？
2. Memory View查看`0xA586-0xA686` (filter数组)

### iteration显示错误值

**原因**: main::SP+6未恢复  
**检查**:
```bash
cat build/pc_ranges.json | grep -A 10 "W001" | grep "main::SP+6"
```

### 0xFFFE被改写

**原因**: 恢复时计算出非法地址  
**已修复**: Stage 11边界检查  
**验证**: 查看`0x6478`和`0x647A`的值

## 备份顺序

```assembly
__WID_W001: MOV.W #1, &ASAP_WID_SAVE      ; ① WID (原子标记)
            MOV.W r12, 4(r1)               ; ② 关键写
            MOV.W 4(r1), &ASAP_SLOT_XX     ; ③ 变量备份
            MOV.W R1, &ASAP_SP_SAVE        ; ④ SP备份
```

## 恢复流程

```
1. Bootloader启动
2. Main函数开头检查ASAP_WID_SAVE
3. 如果WID非0 → 调用_asap_restore
4. _asap_restore查找恢复表
5. 恢复所有变量（带边界检查）
6. 恢复返回地址（如果在子函数）
7. 跳转到恢复PC
```

## 修改定时器间隔

编辑 `Benchmarks/cf/main_cf.c`:
```c
#define min_pf 10        // 最小间隔
random_num = min_pf + (RTCPS % 51) * 8;  // 10-418 ticks
```

## 查看编译中间结果

```bash
# 查看备份候选
cat build/candidates.json | python3 -m json.tool | less

# 查看FRAM槽位分配
cat build/fram_slots.json | python3 -m json.tool | less

# 查看调用图
cat build/call_graph.json | python3 -m json.tool | less

# 查看某个WID的恢复列表
cat build/pc_ranges.json | python3 -m json.tool | grep -A 20 "W001"

# 查看恢复汇编
cat build/asap_restore.s | less
```

## objdump常用命令

```bash
# 查看WID-PC映射
msp430-elf-objdump -d firmware_final.out | grep "__WID_"

# 查看恢复表
msp430-elf-objdump -d firmware_final.out | grep -A 50 "_restore_list_W001"

# 查看函数反汇编
msp430-elf-objdump -d firmware_final.out | grep -A 100 "<insert>:"

# 查看_asap_restore
msp430-elf-objdump -d firmware_final.out | grep -A 200 "<_asap_restore>:"
```

## 排除某个函数/变量

编辑 `Compiler/bc_core_config.json`:
```json
{
  "exclude_functions": [
    "uart_putc",
    "Timer0_B1_ISR",
    "your_function_name"
  ]
}
```

## LED配置

编辑 `Compiler/stage5b_inject_main_restore.py`:
- P1.0 (红灯): `0x0202` (P1OUT), `0x0204` (P1DIR)
- 延时计数器: `0x6476` (FRAM地址)
- 闪烁次数: 3次 (可修改循环)

## 完整文档

详细实现见 `ASAP_IMPLEMENTATION_COMPLETE.md`
