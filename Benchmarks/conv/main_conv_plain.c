#include <msp430.h>
#include <stdio.h>

// UART printf support
#define PRINTF printf

// Timer configuration (if needed)
#ifndef TIMER
#define TIMER 0
#endif

#ifndef LOOP_IDX
#define LOOP_IDX 0
#endif

#if TIMER == 1
// 定时器中断（周期性断电模拟）
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void) {
	PMMCTL0 = PMMPW | PMMSWPOR;  // 触发软件POR
	TBCTL |= TBCLR;              // 清除定时器
}
#endif

// Initialize hardware
void init()
{
	WDTCTL = WDTPW | WDTHOLD;
	PM5CTL0 &= ~LOCKLPM5;

	// P1.2: Performance indicator (init开始时置高)
	P1DIR |= BIT2;
	P1OUT |= BIT2;  // 使用|=避免清除P1.3
	
	// Clock: 8MHz DCO
	CSCTL0_H = 0xA5;
	CSCTL1 = DCOFSEL_6;
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;
	
	// UART: 115200 baud @ 8MHz
	UCA0CTLW0 = UCSWRST;
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_4 | (0x55 << 8);
	
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	UCA0CTLW0 &= ~UCSWRST;

#if TIMER == 1
    // ===== 定时器在 init() 之后启动（确保外设初始化完成）=====
    TBCTL = TBSSEL_1 | ID_3 | MC_2 | TBCLR;  // ACLK(32768Hz), /8=4096Hz, continuous
    TBCCTL1 = CCIE;
#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif
    TBCCR1 = TIMER_VALUE;
    __enable_interrupt();                     // 使能全局中断
#endif
}

// Convolution parameters
//#define N 500
#define N 200
#define K 20

// kernel是const，放全局FRAM只读区域
const unsigned kernel[K] = {
	1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
	1, 1, 1, 1, 1, 1, 1, 1, 1, 1
};

int main()
{
	init();
    
    unsigned vec[N];
    unsigned out[N-K+1];
	while (1) {
		//PRINTF("start\r\n");
		//P1OUT &= ~BIT2;  // 循环开始立即置低（测试）
		
		// Initialize input vector
		for (unsigned i = 0; i < N; ++i)
			vec[i] = i;

		// Initialize output array
		for (unsigned i = 0; i < N-K+1; ++i)
			out[i] = 0;

	// Convolution: K window low-pass filter (幂等版本)
	// kernel全是1，优化掉乘法
	for (unsigned i = 0; i < N-K+1; ++i) {
		unsigned temp = 0;
		for (unsigned j = 0; j < K; ++j)
			temp += vec[i+j];  // 不需要乘以kernel
		out[i] = temp;
	}

		// Print first 5 results
		//or (unsigned i = 0; i < 5; ++i)
			//PRINTF("%u ", out[i]);
		//PRINTF("\r\n");
		
		// 完成一轮：P1.2置低→延迟1ms→置高（和AR一致）
		P1OUT &= ~BIT2;         // 置低（标记完成）
		__delay_cycles(8000);   // 延迟1ms（8MHz时钟）
		P1OUT |= BIT2;          // 置高（准备下一轮）
	}

	return 0;
}

