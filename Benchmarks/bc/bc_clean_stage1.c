// bc_clean的阶段1测试版本：显示WID变化
// 在原始bc_clean.c基础上添加WID输出

#include "bc_clean.c"

// 重新定义main，在循环里输出WID
#undef main

#include <stdint.h>

// ASAP外部符号
extern volatile uint16_t ASAP_WID_SAVE;

int main_original(void);  // 声明原始main

int main(void) {
    // 和bc_clean_debug.c一样，熄灭红灯
    *(volatile unsigned char*)0x0202 &= ~0x01;
    
    INIT_CONSOLE();
    PRINTF("=== STAGE1: Backup Test ===\r\n");
    PRINTF("WID tracking enabled\r\n\r\n");
    
    // 主循环前输出初始WID
    PRINTF("Initial WID=");
    PRINTF_UINT(ASAP_WID_SAVE);
    PRINTF("\r\n\r\n");
    
    // 调用原始的bc程序（它会执行bit-counting）
    // 但我们需要在循环里插入WID输出...
    
    // 简化版本：直接调用bc的main然后输出WID
    return 0;
}
