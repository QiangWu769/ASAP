/*
 * BC Timer Test - 只测试Timer中断是否触发
 */

#include <msp430.h>
#include <stdint.h>
#include <libio/log.h>

#define LOOP_IDX 1
#define SEED 4L
#define ITER 100
#define CHAR_BIT 8

// FRAM持久化变量
static volatile uint16_t __attribute__((section(".persistent"))) pf_counter = 0;
static volatile uint16_t __attribute__((section(".persistent"))) timer_count = 0;

/* Bit count lookup table */
static const char bits[256] =
{
	0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4,
	1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5,
	1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
	1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
	2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6,
	3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
	3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7,
	4, 5, 5, 6, 5, 6, 6, 7, 5, 6, 6, 7, 6, 7, 7, 8
};

unsigned bit_count(uint32_t x)
{
	unsigned n = 0;
	if (x) do n++; while (0 != (x = x&(x-1)));
	return n;
}

int main()
{
	/* 阶段2：进入main - 红灯熄灭，只留绿灯 */
	*(volatile unsigned char*)0x0202 &= ~0x01;  /* P1OUT &= ~BIT0 (红灯灭) */
	
	INIT_CONSOLE();

	PRINTF("MAIN_TIMER_TEST\r\n");
	
	// 输出计数器
	extern volatile uint16_t ASAP_WID_SAVE;
	PRINTF("PF_Counter=");
	PRINTF_UINT(pf_counter);
	PRINTF(" TimerCount=");
	PRINTF_UINT(timer_count);
	PRINTF(" WID=");
	PRINTF_UINT(ASAP_WID_SAVE);
	PRINTF("\r\n");
	
	// 启动Timer
	if (pf_counter == 0) {
		pf_counter = 1;
		timer_count = 0;
		
		// 配置P4.6为输出（用于Timer中断翻转）
		*(volatile unsigned char*)0x0225 |= 0x40;  // P4DIR |= BIT6
		
		// 配置Timer B0 - 使用ACLK (32768Hz), 分频8, 连续模式
		TBCTL = TBSSEL__ACLK | ID__8 | MC__CONTINUOUS | TBCLR;
		TBCCTL1 = CCIE;  // 使能CCR1中断
		TBCCR1 = 4096;   // 约1秒触发一次 (32768/8/4096 ≈ 1Hz)
		
		__enable_interrupt();  // 全局使能中断
		
		PRINTF(">>> Timer ARMED (1Hz) <<<\r\n");
	}
	
	PRINTF("INIT 0 START\r\n");
	
	uint32_t seed = (uint32_t)SEED;
	
	// 只执行一个简单的循环
	for (int i = 0; i < 10; i++) {
		PRINTF("n");
		PRINTF_UINT(i);
		PRINTF(" ");
		PRINTF_UINT(seed & 0xFFFF);
		PRINTF("\r\n");
		
		bit_count(seed);
		seed += 13;
		
		// 每次迭代后输出timer_count
		PRINTF("  [TimerCount=");
		PRINTF_UINT(timer_count);
		PRINTF("]\r\n");
	}
	
	PRINTF("END - Final TimerCount=");
	PRINTF_UINT(timer_count);
	PRINTF("\r\n");
	
	return 0;
}

// Timer中断：翻转P4.6 LED，增加计数器
void TimerB1_ISR(void) {
	timer_count++;  // 增加计数器
	*(volatile unsigned char*)0x0224 ^= 0x40;  // P4OUT ^= BIT6 (翻转绿灯)
	TBCCR1 += 4096;  // 设置下一次触发
	TBCCTL1 &= ~CCIFG;  // 清除中断标志
}

// 手动定义中断向量
__attribute__((section("__interrupt_vector_timer0_b1"),aligned(2)))
void(*__vector_timer0_b1)(void) = TimerB1_ISR;
