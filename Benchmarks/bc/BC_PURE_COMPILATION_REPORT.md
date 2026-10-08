# BC Benchmark 纯净版编译报告

## 文件信息
- **源文件**: `main_bc_pure.c`
- **输出文件**: `bc_pure.out`
- **编译器**: msp430-elf-gcc
- **优化级别**: -O2
- **目标MCU**: msp430fr5969

## ✅ 纯净度验证

### 1. 无ASAP相关符号
```bash
✅ 检查通过：无 backup/restore/checkpoint/wid 等ASAP符号
```

### 2. 代码特征
- ✅ 直接MSP430寄存器操作
- ✅ 无extern init()（ASAP hook点）
- ✅ 无volatile checkpoint强制写
- ✅ 无debug_cntr（改为run_counter，语义更清晰）
- ✅ end_run()只用于标记测试完成

### 3. 保留的必要功能
- ✅ `end_run()`: 打印运行计数，标记测试完成
- ✅ `run_counter`: 记录完成的测试轮数
- ✅ UART输出完整结果

## 📊 预期输出

### LOOP_IDX=3 时的输出：
```
start
end
245
245
245
245
245
245
245
start
end
490
490
490
490
490
490
490
start
end
735
735
735
735
735
735
735
cnt: 3
=== Done ===
```

### 输出说明：
- `start`: 开始一轮测试
- `end`: 结束一轮测试
- 7个数字: n_0 到 n_6 的累计结果（每轮+245）
- `cnt: 3`: 完成3轮测试
- `=== Done ===`: 程序完成

## 🔧 编译命令
```bash
msp430-elf-gcc -mmcu=msp430fr5969 -O2 -Wall -o bc_pure.out main_bc_pure.c
```

## 📝 与main_bc_chinchilla.c的区别

| 特性 | main_bc_chinchilla.c | main_bc_pure.c |
|------|---------------------|----------------|
| ASAP支持 | ❌ 有残留 | ✅ 完全移除 |
| init()调用 | 有（ASAP hook） | 无（直接init_hardware） |
| volatile checkpoint | 有 | 无 |
| debug_cntr | ASAP计数器 | 改为run_counter |
| PC检查注释 | 有 | 无 |
| 代码行数 | 272行 | 251行 |
| 编译产物大小 | - | 22KB |

## ✅ 结论
`bc_pure.out` 是**真正的纯净版BC测试程序**，不包含任何ASAP备份/恢复逻辑。

生成时间: $(date)
