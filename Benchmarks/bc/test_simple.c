#include <stdint.h>
#include "../../Runtime/src/uart.h"

void init(void);

int main(void) {
	init();  // 初始化外设
	
	// 调试输出
	if (*(volatile uint16_t *)0x7000 == 0xFFFF) {
		PRINTF("COLD\r\n");
	} else {
		PRINTF("HOT:");
		uart_print_uint(*(volatile uint16_t *)0x7000);
		PRINTF("\r\n");
	}
	// ← stage5b会在这里之后注入PC跳转逻辑
	
	// 只初始化一次（在main开头）
	unsigned n_0 = 0;
	unsigned n_1 = 0;
	unsigned i;
	
	PRINTF("=== Start Test ===\r\n");
	
	// 简单循环：累加10次，每次+100
	for (i = 0; i < 10; i++) {
		n_0 += 100;
		n_1 = i + 1;  // n_1记录当前循环次数
		
		PRINTF("i=");
		uart_print_uint(i);
		PRINTF(" n_0=");
		uart_print_uint(n_0);
		PRINTF("\r\n");
		
		// 在i=5时触发断电
		if (i == 5) {
			// 检查FRAM计数器
			unsigned por_cnt;
			__asm__ volatile ("MOV.W &0x7200, %0\n" : "=r"(por_cnt));
			
			if (por_cnt == 0xFFFF) {
				__asm__ volatile ("MOV.W #0, &0x7200\n");
				por_cnt = 0;
			}
			
			if (por_cnt == 0) {
				PRINTF(">>> TRIGGER POR at i=5 <<<\r\n");
				__asm__ volatile (
					"MOV.W #1, &0x7200\n"
					"NOP\nNOP\nNOP\nNOP\nNOP\n"
					"MOV.W #0x6904, &0x0120\n"
					"1: JMP 1b\n"
				);
			}
		}
	}
	
	PRINTF("=== Test Complete ===\r\n");
	PRINTF("Final n_0=");
	uart_print_uint(n_0);
	PRINTF(" (expected 1000)\r\n");
	PRINTF("Final n_1=");
	uart_print_uint(n_1);
	PRINTF(" (expected 10)\r\n");
	
	while(1);
	return 0;
}











