#ifndef ALPACA_H
#define ALPACA_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <libmsp/mem.h>
#define end_run() PRINTF("cnt: %u\r\n", debug_cntr); debug_cntr = 0;

extern unsigned* volatile cur_reg;
void restore_regs();
extern void init();
extern uint8_t chkpt_ever_taken;
extern volatile unsigned regs_0[16];
extern volatile unsigned regs_1[16];
extern unsigned debug_cntr;

#endif // ALPACA_H
