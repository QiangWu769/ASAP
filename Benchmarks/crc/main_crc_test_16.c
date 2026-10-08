#include <msp430.h>
#include <string.h>

// BITSET宏定义
#define BITSET(port, val) ((port) |= (val))

// TIMER is defined by Makefile: -DTIMER=0 or -DTIMER=1
#ifndef TIMER
#define TIMER 0
#endif

// #ifdef PF_SIMULATION
// #define min_pf 10
// __attribute__((section(".upper.noinit"))) int timer_count = 500;
// __attribute__((section(".upper.noinit"))) volatile unsigned int random_num; // read temperature value
// __attribute__((section(".upper.noinit"))) int mod5_rand;
// #endif

#if TIMER == 1
// ========== 定时器中断（周期性断电）==========
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void){
	PMMCTL0 = PMMPW | PMMSWPOR;  // 触发软件POR，模拟断电
	TBCTL |= TBCLR;              // 清除定时器（POR会复位一切）
}
#endif

// ============================================================================
// CRC Implementation (完整保留原始实现，不简化)
// ============================================================================

#define FALSE	0
#define TRUE	!FALSE

// CRC-CCITT配置
typedef unsigned short  crc;
#define CRC_NAME			"CRC-CCITT"
#define POLYNOMIAL			0x1021
#define INITIAL_REMAINDER	0xFFFF
#define FINAL_XOR_VALUE		0x0000
#define REFLECT_DATA		FALSE
#define REFLECT_REMAINDER	FALSE
#define CHECK_VALUE			0x29B1

#define WIDTH    (8 * sizeof(crc))
#define TOPBIT   (1 << (WIDTH - 1))

#if (REFLECT_DATA == TRUE)
#undef  REFLECT_DATA
#define REFLECT_DATA(X)			((unsigned char) reflect((X), 8))
#else
#undef  REFLECT_DATA
#define REFLECT_DATA(X)			(X)
#endif

#if (REFLECT_REMAINDER == TRUE)
#undef  REFLECT_REMAINDER
#define REFLECT_REMAINDER(X)	((crc) reflect((X), WIDTH))
#else
#undef  REFLECT_REMAINDER
#define REFLECT_REMAINDER(X)	(X)
#endif

// CRC查表（Fast实现用）
// 【测试】改为普通SRAM全局数组，测试ASAP能否识别
// 注意：不能用static，否则恢复代码无法引用符号
crc crcTable[256];

/*********************************************************************
 * Function:    reflect()
 * Description: Reorder the bits of a binary sequence, by reflecting
 *				them about the middle position.
 *********************************************************************/
static unsigned long
reflect(unsigned long data, unsigned char nBits)
{
	unsigned long  reflection = 0x00000000;
	unsigned char  bit;

	// Reflect the data about the center bit.
	for (bit = 0; bit < nBits; ++bit)
	{
		// If the LSB bit is set, set the reflection of it.
		if (data & 0x01)
		{
			reflection |= (1 << ((nBits - 1) - bit));
		}

		data = (data >> 1);
	}

	return (reflection);

}	/* reflect() */


/*********************************************************************
 * Function:    crcSlow()
 * Description: Compute the CRC of a given message (逐位计算，慢但简单)
 *********************************************************************/
crc
crcSlow(unsigned char const message[], int nBytes)
{
    crc            remainder = INITIAL_REMAINDER;
	int            byte;
	unsigned char  bit;


    // Perform modulo-2 division, a byte at a time.
    for (byte = 0; byte < nBytes; ++byte)
    {
        // Bring the next byte into the remainder.
        remainder ^= (REFLECT_DATA(message[byte]) << (WIDTH - 8));

        // Perform modulo-2 division, a bit at a time.
        for (bit = 8; bit > 0; --bit)
        {
            // Try to divide the current data bit.
            if (remainder & TOPBIT)
            {
                remainder = (remainder << 1) ^ POLYNOMIAL;
            }
            else
            {
                remainder = (remainder << 1);
            }
        }
    }

    // The final remainder is the CRC result.
    return (REFLECT_REMAINDER(remainder) ^ FINAL_XOR_VALUE);

}   /* crcSlow() */


/*********************************************************************
 * Function:    crcInit()
 * Description: Populate the partial CRC lookup table.
 *********************************************************************/
void
crcInit(void)
{
    crc			   remainder;
	int			   dividend;
	unsigned char  bit;


    // Compute the remainder of each possible dividend.
    for (dividend = 0; dividend < 256; ++dividend)
    {
        // Start with the dividend followed by zeros.
        remainder = dividend << (WIDTH - 8);

        // Perform modulo-2 division, a bit at a time.
        for (bit = 8; bit > 0; --bit)
        {
            // Try to divide the current data bit.
            if (remainder & TOPBIT)
            {
                remainder = (remainder << 1) ^ POLYNOMIAL;
            }
            else
            {
                remainder = (remainder << 1);
            }
        }

        // Store the result into the table.
        crcTable[dividend] = remainder;
    }

}   /* crcInit() */


/*********************************************************************
 * Function:    crcFast()
 * Description: Compute the CRC of a given message (查表法，快速)
 *********************************************************************/
crc
crcFast(unsigned char const message[], int nBytes)
{
    crc	           remainder = INITIAL_REMAINDER;
    unsigned char  data;
	int            byte;


    // Divide the message by the polynomial, a byte at a time.
    for (byte = 0; byte < nBytes; ++byte)
    {
        data = REFLECT_DATA(message[byte]) ^ (remainder >> (WIDTH - 8));
  		remainder = crcTable[data] ^ (remainder << 8);
    }

    // The final remainder is the CRC result.
    return (REFLECT_REMAINDER(remainder) ^ FINAL_XOR_VALUE);

}   /* crcFast() */


// ============================================================================
// UART & Printf实现（已注释 - main循环中未使用）
// ============================================================================

// void uart_putchar(char c)
// {
// 	while(!(UCA0IFG & UCTXIFG));
// 	UCA0TXBUF = c;
// }

// static char hex_char(unsigned char nibble)
// {
// 	return (nibble < 10) ? ('0' + nibble) : ('A' + nibble - 10);
// }

// void print_hex(unsigned int value)
// {
// 	uart_putchar('0');
// 	uart_putchar('x');
// 	uart_putchar(hex_char((value >> 12) & 0xF));
// 	uart_putchar(hex_char((value >> 8) & 0xF));
// 	uart_putchar(hex_char((value >> 4) & 0xF));
// 	uart_putchar(hex_char(value & 0xF));
// }

// void uart_puts(const char* str)
// {
// 	while(*str) {
// 		uart_putchar(*str++);
// 	}
// }

// ============================================================================
// Init & Main
// ============================================================================

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

    // 定时器初始化移到了 main() 中，在 init() 之后启动
#if TIMER == 1
    // ===== 定时器在 init() 之后启动（确保外设初始化完成）=====
    TBCTL = TBSSEL_1 | ID_3 | MC_2 | TBCLR;  // ACLK(32768Hz), /8=4096Hz, continuous
    TBCCTL1 = CCIE;                           // 使能CCR1中断
#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif
    TBCCR1 = TIMER_VALUE;                     // 设置比较值
    __enable_interrupt();                     // 使能全局中断
#endif
}

int main(void)
{
	init();

	
	crc result_slow, result_fast;
	unsigned char test[] = "123456789";
	
	// ===== 循环执行 =====
	while(1) {
		// Slow CRC
		result_slow = crcSlow(test, strlen((const char*)test));
		
		crcInit();
		// Fast CRC
		result_fast = crcFast(test, strlen((const char*)test));
		
		// 一轮完成：P1.2置低再置高（生成脉冲）
		P1OUT &= ~BIT2;        // 置低
		__delay_cycles(8000);  // 1ms延迟 @8MHz
		P1OUT |= BIT2;         // 置高
	}
	
	return 0;
}

