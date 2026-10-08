#include <stdarg.h>
#include <string.h>
#include <libio/log.h>
#include <msp430.h>

#include "ratchet.h"

//extern void checkpoint();

__nv uint8_t isStuck = 0;
__nv volatile unsigned regs_0[16];
__nv volatile unsigned regs_1[16];

__nv unsigned* volatile cur_reg = regs_0;

__nv uint8_t chkpt_ever_taken = 0;
__nv unsigned debug_cntr = 0;
void checkpoint();

/**
 * @brief checkpoint regs
 * Unlike Chinchilla, Ratchet checkpoint can be located at backend
 * To anywhere, so we should not mess up any registers (even r15, for example)
 */
void checkpoint() {
	unsigned r12;
	/* When you call this function:
	 * LR gets stored in Stack
	 * R4 gets stored in Stack
	 * then 6 byte is for local var
	 * R12 gets stored in Stack
	 * SP gets saved to R4
	 *
	 * */
	__asm__ volatile ("PUSH R12"); // we will use R12 for saving cur_reg
	__asm__ volatile ("MOV %0, R12" :"=m"(cur_reg));

	// current status!
	/*
	 * |							| <- Prev-r1 (r1 + 12)
	 * |		lr (r0)		| <- 10(r1)
	 * |			r4			| <- 8(r1)
	 * |	local var		| <- 6(r1)
	 * |	local var		| <- 4(r1)
	 * |	local var		| <- 2(r1)
	 * |			r12			| <- r1
	 */
	__asm__ volatile ("MOV 10(R1), 0(R12)"); // LR is going to be the next PC

	__asm__ volatile ("MOV R1, 2(R12)"); // We need to add 12 to get the prev SP
	__asm__ volatile ("MOV R2, 4(R12)");
	__asm__ volatile ("ADD #12, 2(R12)");
	__asm__ volatile ("MOV 8(R1), 6(R12)"); // R4
	__asm__ volatile ("MOV R5, 8(R12)");
	__asm__ volatile ("MOV R6, 10(R12)");
	__asm__ volatile ("MOV R7, 12(R12)");
	__asm__ volatile ("MOV R8, 14(R12)");
	__asm__ volatile ("MOV R9, 16(R12)");
	__asm__ volatile ("MOV R10, 18(R12)");
	__asm__ volatile ("MOV R11, 20(R12)");

	__asm__ volatile ("MOV 0(R1), 22(R12)");
	__asm__ volatile ("MOV R13, 24(R12)");
	__asm__ volatile ("MOV R14, 26(R12)");
	__asm__ volatile ("MOV R15, 28(R12)");

	__asm__ volatile ("MOV R12, %0":"=m"(r12));
	// double-buffer the checkpoint
	cur_reg = (cur_reg == regs_0 ? regs_1 : regs_0);
	isStuck = 0;
	debug_cntr++;
	__asm__ volatile ("MOV %0, R12":"=m"(r12));

	// Adjust stack pointer manually because
	// instead of return, we will use
	// mov to return
	__asm__ volatile ("MOV 2(R12), R1");

	__asm__ volatile ("MOV 4(R12), R2");
	__asm__ volatile ("MOV 24(R12), R13");
	__asm__ volatile ("MOV 26(R12), R14");
	__asm__ volatile ("MOV 28(R12), R15");
	// Now the state is...
	/*
	 * |							| <- r1
	 * |		lr (r0)		| <- -2(r1)
	 * |			r4			| <- -4(r1)
	 * |	local var		| <- -6(r1)
	 * |	local var		| <- -8(r1)
	 * |	local var		| <- -10(r1)
	 * |			r12			| <- -12(r1)
	 */
	// instead of pop, use mov
	__asm__ volatile ("MOV -4(R1), R4");
	__asm__ volatile ("MOV -12(R1), R12");
	// this is instead of return
	// All of these are happening because we do
	// not want the auto sp adjustment to
	// mess up the status reg
	// (e.g., incd r1 will change the status reg)
	__asm__ volatile ("MOV -2(R1), R0");
}


/**
 * @brief restore regs
 */
void restore_regs() {
	unsigned* prev_reg;
	if (!chkpt_ever_taken) {
		chkpt_ever_taken = 1;
		return;
	}
	else if (cur_reg == regs_0) {
		prev_reg = regs_1;
	}
	else {
		prev_reg = regs_0;
	}
	if (isStuck == 1) {
		P1OUT |= BIT4;
		P1OUT &= ~BIT4;
	}
	isStuck = 1;

	__asm__ volatile ("MOV %0, R12" :"=m"(prev_reg));
	// TODO: do we need R15 - R12? Lets not
	__asm__ volatile ("MOV 28(R12), R15");
	__asm__ volatile ("MOV 26(R12), R14");
	__asm__ volatile ("MOV 24(R12), R13");
	__asm__ volatile ("MOV 20(R12), R11");
	__asm__ volatile ("MOV 18(R12), R10");
	__asm__ volatile ("MOV 16(R12), R9");
	__asm__ volatile ("MOV 14(R12), R8");
	__asm__ volatile ("MOV 12(R12), R7");
	__asm__ volatile ("MOV 10(R12), R6");
	__asm__ volatile ("MOV 8(R12), R5");
	__asm__ volatile ("MOV 6(R12), R4");
	__asm__ volatile ("MOV 4(R12), R2");
	__asm__ volatile ("MOV 2(R12), R1");
	// For temp solution, 0x4400 is reserved
	// for saving pc on restore.
	// This is because as soon as R4 gets
	// restored, we cannot use stack anymore
	//__asm__ volatile ("MOV 0(R12), %0" :"=m"(pc));
	__asm__ volatile ("MOV 0(R12), &0x4400");
	__asm__ volatile ("MOV 22(R12), R12");
	__asm__ volatile ("MOV &0x4400, R0");
	//__asm__ volatile ("MOV %0, R0" :"=m"(pc));
}
