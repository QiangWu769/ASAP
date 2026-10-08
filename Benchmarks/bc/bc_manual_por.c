/*
 * BC Power Failure Test - Manual POR Version
 * 不使用Timer中断，直接在代码中触发软件POR
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

/* BC Algorithm 1: Bit Count */
unsigned bit_count(uint32_t x)
{
	unsigned n = 0;
	if (x) do n++; while (0 != (x = x&(x-1)));
	return n;
}

/* BC Algorithm 2: Bitcount */
unsigned bitcount(uint32_t x)
{
	unsigned n = 0;
	unsigned char *p = (unsigned char*)&x;
	n += bits[p[0]] + bits[p[1]] + bits[p[2]] + bits[p[3]];
	return n;
}

/* BC Algorithm 3: ntbl_bitcnt */
unsigned ntbl_bitcnt(uint32_t x)
{
	return bits[(unsigned char)x] +
	       bits[(unsigned char)(x>>8)] +
	       bits[(unsigned char)(x>>16)] +
	       bits[(unsigned char)(x>>24)];
}

/* BC Algorithm 4: ntbl_bitcount */
unsigned ntbl_bitcount(uint32_t x)
{
	return (bits[(unsigned char)x] +
	        bits[(unsigned char)(x>>8)] +
	        bits[(unsigned char)(x>>16)] +
	        bits[(unsigned char)(x>>24)]);
}

/* BC Algorithm 5: BW_btbl_bitcount */
unsigned BW_btbl_bitcount(uint32_t x)
{
	union {
		unsigned char ch[4];
		uint32_t x;
	} U;
	U.x = x;
	return bits[U.ch[0]] + bits[U.ch[1]] + bits[U.ch[2]] + bits[U.ch[3]];
}

/* BC Algorithm 6: AR_btbl_bitcount */
unsigned AR_btbl_bitcount(uint32_t x)
{
	unsigned char *Ptr = (unsigned char *)&x;
	unsigned Accu = bits[*Ptr++];
	Accu += bits[*Ptr++];
	Accu += bits[*Ptr++];
	return Accu + bits[*Ptr];
}

// Timer B0中断服务程序（ISR）- 触发软件复位（PUC）
__attribute__((interrupt(TIMER0_B0_VECTOR)))
void Timer_B0_ISR(void)
{
	// 触发软件复位（通过PMMCTL0写入无效密码）
	// 用内联汇编避免被插桩
	__asm__ volatile (
		"MOV.W #0x0000, &0x0120\n"  // PMMCTL0 = 0x0000（错误密码触发PUC复位）
		: : : "memory"
	);
	
	// 不会执行到这里
	while(1);
}

/* Main test loop */
int main()
{
	/* 阶段2：进入main - 红灯熄灭，只留绿灯 */
	/* 用内联汇编避免被插桩 */
	__asm__ volatile ("BIC.B #1, &0x0202\n");  /* P1OUT &= ~BIT0 (红灯灭) */
	
	INIT_CONSOLE();  // Initialize output hardware

	PRINTF("MAIN_V2\r\n");
	
	// 输出断电计数器和WID
	extern volatile uint16_t ASAP_WID_SAVE;
	PRINTF("PF_Counter=");
	PRINTF_UINT(pf_counter);
	PRINTF(" WID_Now=");
	PRINTF_UINT(ASAP_WID_SAVE);
	PRINTF("\r\n");
	
	// 第一次执行（冷启动）
	if (pf_counter == 0) {
		PRINTF(">>> First Run - Will trigger POR after F0 n2 <<<\r\n");
		pf_counter = 1;
	} else {
		// 第二次执行（热启动/恢复）
		PRINTF(">>> RECOVERED! Continuing from saved state <<<\r\n");
		// 【验证】恢复标记（内联汇编，不会被插桩）
		__asm__ volatile ("MOV.W #0xBEEF, &0x7108\n");
	}
	
	PRINTF("INIT 0 START\r\n");
	
	uint32_t seed = (uint32_t)SEED;
	
	for (int func = 0; func < 7; func++) {
		PRINTF("F");
		PRINTF_UINT(func);
		PRINTF("\r\n");
		
		uint32_t n_0 = 0, n_1 = 0, n_2 = 0, n_3 = 0, n_4 = 0, n_5 = 0, n_6 = 0;
		
	for (int i = 0; i < ITER; i++) {
		// 【验证】恢复后第一次执行i==2时记录实际值（内联汇编）
		if (pf_counter >= 2 && i == 2 && func == 0) {
			static volatile int first_time = 1;
			if (first_time) {
				__asm__ volatile (
					"MOV.W %0, &0x7110\n"  // 实际i
					"MOV.W %1, &0x7112\n"  // 实际seed低位
					"MOV.W %2, &0x7114\n"  // 实际seed高位
					"MOV.W %3, &0x7116\n"  // 实际func
					:
					: "r"((uint16_t)i), "r"((uint16_t)(seed & 0xFFFF)),
					  "r"((uint16_t)(seed >> 16)), "r"((uint16_t)func)
				);
				first_time = 0;
			}
		}
		
		PRINTF("n");
		PRINTF_UINT(i);
		PRINTF(" ");
		PRINTF_UINT(seed & 0xFFFF);
		PRINTF("\r\n");
			
			if(func == 0) {
				n_0 += bit_count(seed);
			} else if(func == 1) {
				n_1 += bitcount(seed);
			} else if(func == 2) {
				n_2 += ntbl_bitcnt(seed);
			} else if(func == 3) {
				n_3 += ntbl_bitcount(seed);
			} else if(func == 4) {
				n_4 += BW_btbl_bitcount(seed);
			} else if(func == 5) {
				n_5 += AR_btbl_bitcount(seed);
			}
			
		seed += 13;  // 这个写操作会触发备份
	
	// 【验证】用内联汇编写FRAM（不会被插桩）
	if (func == 0 && i == 2) {
		__asm__ volatile (
			"MOV.W %0, &0x7100\n"  // i=2
			"MOV.W %1, &0x7102\n"  // seed低位=43
			"MOV.W %2, &0x7104\n"  // seed高位=0
			"MOV.W %3, &0x7106\n"  // func=0
			:
			: "r"((uint16_t)i), "r"((uint16_t)(seed & 0xFFFF)), 
			  "r"((uint16_t)(seed >> 16)), "r"((uint16_t)func)
		);
	}
	
	// 【Timer中断触发复位模拟断电】在seed += 13之后，循环内部触发
	if (pf_counter == 1 && func == 0 && i == 2) {
		PRINTF(">>> TRIGGER TIMER RESET NOW! <<<\r\n");
		pf_counter = 2;  // 标记已触发
		
		// 配置Timer B触发复位（用内联汇编避免被插桩）
		__asm__ volatile (
			"MOV.W #0x0200, &0x0380\n"  // TB0CTL: TBCLR, 清除计数器
			"MOV.W #1, &0x0392\n"       // TB0CCR0 = 1（很短的时间）
			"MOV.W #0x0214, &0x0380\n"  // TB0CTL: SMCLK, Up mode, Enable interrupt
			"MOV.W #0x0010, &0x0382\n"  // TB0CCTL0: Enable interrupt
			"NOP\n"
			"NOP\n"
			: : : "memory"
		);
		
		// 等待中断触发复位
		__asm__ volatile ("BIS.W #8, R2\n");  // Enable interrupts (GIE)
		while(1);  // 等待中断
	}
	}
		
		PRINTF("end ");
		PRINTF_UINT(seed & 0xFFFF);
		PRINTF("\r\n");
	}
	
	// 输出最终WID
	PRINTF(" WID=");
	PRINTF_UINT(ASAP_WID_SAVE);
	PRINTF("\r\n");
	PRINTF(">>> ALL DONE! <<<\r\n");
	
	return 0;
}
