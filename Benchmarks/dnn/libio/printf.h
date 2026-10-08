#ifndef LIBIO_PRINTF_H
#define LIBIO_PRINTF_H

/* Simplified - no complex conditionals */
#include <msp430.h>

/* Simple UART output functions */
static inline void _uart_putc(char c)
{
	while (!(UCA0IFG & UCTXIFG));
	UCA0TXBUF = c;
}

static inline void _uart_puts(const char *s)
{
	while (*s) _uart_putc(*s++);
}

static inline void _uart_print_uint(unsigned int n)
{
	char buf[11];
	int i = 0;
	
	if (n == 0) {
		_uart_putc('0');
		return;
	}
	
	while (n > 0) {
		buf[i++] = '0' + (n % 10);
		n /= 10;
	}
	
	while (i > 0) _uart_putc(buf[--i]);
}

/* Initialize UART */
static inline void INIT_CONSOLE(void)
{
	WDTCTL = WDTPW | WDTHOLD;
	
	// 配置时钟为8MHz
	CSCTL0_H = 0xA5;
	CSCTL1 = DCORSEL | DCOFSEL_3;  // DCO = 8MHz
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;  // ACLK=XT1, SMCLK=DCO, MCLK=DCO
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;  // 不分频
	
	// 配置UART: 8MHz / 16 / 4.34 ≈ 115200 bps
	UCA0CTLW0 = UCSWRST;
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;           // 8MHz / 16 / 115200 = 4.34
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_5 | (0x55 << 8);  // 过采样x16, UCBRF=5, UCBRS=0x55
	
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	UCA0CTLW0 &= ~UCSWRST;
	PM5CTL0 &= ~LOCKLPM5;
}

/* Simple PRINTF - just outputs strings */
#define PRINTF(str) _uart_puts(str)
#define PRINTF_UINT(n) _uart_print_uint(n)

/* Dummy definitions for compatibility */
#define BLOCK_PRINTF_BEGIN()
#define BLOCK_PRINTF(...)
#define BLOCK_PRINTF_END()

#endif // LIBIO_PRINTF_H
