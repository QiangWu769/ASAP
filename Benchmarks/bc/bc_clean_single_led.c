#include <msp430.h>
#include "printf.h"

// 简化版bc - 只在main开头控制LED，然后正常输出
static void led_slow_flash_once() {
    // 慢闪一次（表示：进入main）
    P4OUT |= BIT6;
    volatile unsigned int i = 0xFFFF;
    while(i--);
    P4OUT &= ~BIT6;
    i = 0xFFFF;
    while(i--);
}

int main()
{
    // 阶段2：进入main - 慢闪P4.6
    led_slow_flash_once();
    led_slow_flash_once();
    led_slow_flash_once();
    
    // 然后正常初始化UART并输出
    INIT_CONSOLE();
    
    PRINTF("MAIN_V2\r\n");
    PRINTF("BIT_CNT_1\r\n");
    PRINTF("n_0 BW  : 502502start end\r\n");
    
    // 持续输出测试
    unsigned int counter = 0;
    while(1) {
        PRINTF("Loop ");
        PRINTF_UINT(counter);
        PRINTF("\r\n");
        counter++;
        
        // 延时
        volatile unsigned long delay = 500000;
        while(delay--);
    }
    
    return 0;
}
