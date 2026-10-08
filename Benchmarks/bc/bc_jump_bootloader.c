/*
 * BC Test - 直接跳回Bootloader测试恢复逻辑
 */

#include <msp430.h>
#include <stdint.h>
#include <libio/log.h>

#define LOOP_IDX 1
#define SEED 4L
#define ITER 100
#define CHAR_BIT 8

// FRAM持久化变量
__attribute__((section(".persistent"))) volatile uint16_t pf_counter = 0;

// 外部符号：bootloader入口
extern void bootloader_entry(void);

// 位计数函数
int bit_count(long x) {
	int n = 0;
	if (x) do n++; while (0 != (x = x&(x-1)));
	return n;
}

int bitcount(long i) {
	i = ((i & 0xAAAAAAAAL) >>  1) + (i & 0x55555555L);
	i = ((i & 0xCCCCCCCCL) >>  2) + (i & 0x33333333L);
	i = ((i & 0xF0F0F0F0L) >>  4) + (i & 0x0F0F0F0FL);
	i = ((i & 0xFF00FF00L) >>  8) + (i & 0x00FF00FFL);
	i = ((i & 0xFFFF0000L) >> 16) + (i & 0x0000FFFFL);
	return (int)i;
}

int main(void) {
	
	INIT_CONSOLE();  // Initialize output hardware

	PRINTF("MAIN_V2\r\n");
	
	// 输出断电计数器
	PRINTF("PF_Counter=");
	PRINTF_UINT(pf_counter);
	PRINTF("\r\n");
	
	// 第一次执行（冷启动）
	if (pf_counter == 0) {
		PRINTF(">>> First Run - Will jump to bootloader after F0 n2 <<<\r\n");
		pf_counter = 1;
	} else {
		// 第二次执行（热启动/恢复）
		PRINTF(">>> RECOVERED! Continuing from saved state <<<\r\n");
	}
	
	PRINTF("INIT 0 START\r\n");
	
	uint32_t seed = (uint32_t)SEED;
	
	for (int func = 0; func < 7; func++) {
		PRINTF("F");
		PRINTF_UINT(func);
		PRINTF("\r\n");
		
		uint32_t n_0 = 0, n_1 = 0;
		
		for (int i = 0; i < ITER; i++) {
			PRINTF("n");
			PRINTF_UINT(i);
			PRINTF(" ");
			PRINTF_UINT(seed & 0xFFFF);
			PRINTF("\r\n");
			
			if(func == 0) {
				n_0 += bit_count(seed);
			} else if(func == 1) {
				n_1 += bitcount(seed);
			}
			
			seed += 13;  // 这个写操作会触发备份
			
			// 【手动跳回bootloader】在 seed += 13 之后（备份已完成）
			if (pf_counter == 1 && func == 0 && i == 2) {
				PRINTF(">>> JUMP TO BOOTLOADER NOW! <<<\r\n");
				pf_counter = 2;  // 标记已触发，避免恢复后再次触发
				__delay_cycles(100000);  // 延迟让UART输出完成
				
				// 闪灯提示：要跳回bootloader了
				P1OUT |= BIT0;   // 绿灯亮
				P4OUT |= BIT6;   // 红灯亮
				__delay_cycles(1000000);
				P1OUT &= ~BIT0;  // 绿灯灭
				P4OUT &= ~BIT6;  // 红灯灭
				__delay_cycles(1000000);
				P1OUT |= BIT0;   // 绿灯亮
				P4OUT |= BIT6;   // 红灯亮
				__delay_cycles(1000000);
				
				// 直接跳转到bootloader入口！
				bootloader_entry();
				
				// 不会执行到这里
				while(1);
			}
		}
		
		PRINTF("end ");
		PRINTF_UINT(seed & 0xFFFF);
		PRINTF("\r\n");
	}
	
	PRINTF("DONE\r\n");
	
	while(1) {
		__delay_cycles(100000);
	}
}













