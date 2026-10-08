	.text
	.globl checkpoint
	.type checkpoint, @function
checkpoint:
	; first, move sp to 0x2400
	; (checkpoint use volatile stack)
	mov.w	#9216, R1
	push.w	r4
	mov.w	r1, r4
	sub.w	#6, r1
	;APP
	PUSH R12
	;NO_APP
	;APP
	MOV cur_reg, R12
	;NO_APP
	;APP
	MOV 10(R1), 0(R12)
	;NO_APP
	;APP
	MOV R1, 2(R12)
	;NO_APP
	;APP
	MOV R2, 4(R12)
	;NO_APP
	;APP
	ADD #12, 2(R12)
	;NO_APP
	;APP
	MOV 8(R1), 6(R12)
	;NO_APP
	;APP
	MOV R5, 8(R12)
	;NO_APP
	;APP
	MOV R6, 10(R12)
	;NO_APP
	;APP
	MOV R7, 12(R12)
	;NO_APP
	;APP
	MOV R8, 14(R12)
	;NO_APP
	;APP
	MOV R9, 16(R12)
	;NO_APP
	;APP
	MOV R10, 18(R12)
	;NO_APP
	;APP
	MOV R11, 20(R12)
	;NO_APP
	;APP
	MOV 0(R1), 22(R12)
	;NO_APP
	;APP
	MOV R13, 24(R12)
	;NO_APP
	;APP
	MOV R14, 26(R12)
	;NO_APP
	;APP
	MOV R15, 28(R12)
	;NO_APP
	;APP
	MOV R12, -2(r4)
	;NO_APP
	mov.w	&cur_reg, r12
	mov.w	#regs_0, r13
	mov.w	#regs_1, r14
	cmp.w	r13, r12
	mov.w	r13, -4(r4)             ; 2-byte Folded Spill
	mov.w	r14, -6(r4)             ; 2-byte Folded Spill
	jeq	.LBB26_2
; BB#1:                                 ; %entry
	mov.w	-4(r4), r12             ; 2-byte Folded Reload
	mov.w	r12, -6(r4)             ; 2-byte Folded Spill
.LBB26_2:                               ; %entry
	mov.w	-6(r4), r12             ; 2-byte Folded Reload
	mov.w	r12, &cur_reg
	;APP
	MOV -2(r4), R12
	;NO_APP
	;APP
	MOV 2(R12), R1
	;NO_APP
	;APP
	MOV 4(R12), R2
	;NO_APP
	;APP
	MOV 24(R12), R13
	;NO_APP
	;APP
	MOV 26(R12), R14
	;NO_APP
	;APP
	MOV 28(R12), R15
	;NO_APP
	;APP
	MOV -4(R1), R4
	;NO_APP
	;APP
	MOV -12(R1), R12
	;NO_APP
	;APP
	MOV -2(R1), R0
	;NO_APP
	add.w	#6, r1
	pop.w	r4
	ret












    push	r4		;
    mov	r1,	r4	;
		push	r1		; save r1. Pop to retrieve r1
								; later instead of incd'ing r1
    decd	r1		;
    push	r12		;
    mov	&0x52f2,r12	;0x52f2
    mov	@r12,	r12	;
	/*
	 * |							| <- Prev-r1 (r1 + 8)
	 * |		lr (r0)		| <- 6(r1)
	 * |			r4			| <- 4(r1)
	 * |	local use		|
	 * |			r12			| <- r1
	 */
    mov	6(r1),	0(r12)	;
    mov	r1,	2(r12)	;
    add	#8,	2(r12)	;r2 As==11
    mov	r2,	4(r12)	;
    mov	4(r1),	6(r12)	;
    mov	r5,	8(r12)	;
    mov	r6,	10(r12)	; 0x000a
    mov	r7,	12(r12)	; 0x000c
    mov	r8,	14(r12)	; 0x000e
    mov	r9,	16(r12)	; 0x0010
    mov	r10,	18(r12)	; 0x0012
    mov	r11,	20(r12)	; 0x0014
    mov	@r1,	22(r12)	; 0x0016
    mov	r13,	24(r12)	; 0x0018
    mov	r14,	26(r12)	; 0x001a
    mov	r15,	28(r12)	; 0x001c
    mov	r12,	-2(r4)	; 0xfffe
    mov	-2(r4),	r12	;
    mov	4(r12),	r2	;
    mov	24(r12),r13	;0x00018
    mov	26(r12),r14	;0x0001a
    mov	28(r12),r15	;0x0001c
    pop	r12		;
    incd	r1		;
    pop	r4		;
    ret
