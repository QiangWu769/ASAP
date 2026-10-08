/* Simple UART output - lightweight printf replacement */
#ifndef BC_OUTPUT_H
#define BC_OUTPUT_H

#include <msp430.h>

/* Output single character */
static inline void uart_putc(char c)
{
	while (!(UCA0IFG & UCTXIFG));
	UCA0TXBUF = c;
}

/* Output string */
static inline void uart_puts(const char *s)
{
	while (*s) uart_putc(*s++);
}

/* Output unsigned integer */
static inline void uart_print_uint(unsigned int n)
{
	char buf[11];
	int i = 0;
	
	if (n == 0) {
		uart_putc('0');
		return;
	}
	
	while (n > 0) {
		buf[i++] = '0' + (n % 10);
		n /= 10;
	}
	
	while (i > 0) uart_putc(buf[--i]);
}

/* Initialize UART hardware */
static inline void uart_init(void)
{
	WDTCTL = WDTPW | WDTHOLD;
	
	CSCTL0_H = 0xA5;
	CSCTL1 = DCORSEL | DCOFSEL_3;
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;
	
	UCA0CTLW0 = UCSWRST;
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_4 | (0x55 << 8);
	
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	UCA0CTLW0 &= ~UCSWRST;
	PM5CTL0 &= ~LOCKLPM5;
}

/* Macro for clean code - looks like Chinchilla's PRINTF */
#define PRINTF(fmt, ...) uart_puts(fmt)
#define PRINTF_UINT(n) uart_print_uint(n)

#endif





































