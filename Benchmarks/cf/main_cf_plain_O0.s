	.file	"main_cf_plain.c"
.text
	.balign 2
	.type	djb_hash, @function
djb_hash:
; start of function
; framesize_regs:     4
; framesize_locals:   10
; framesize_outgoing: 0
; framesize:          14
; elim ap -> fp       6
; elim fp -> sp       10
; saved regs: R8 R9
	; start of prologue
	PUSHM.W	#2, R9
	SUB.W	#10, R1
	; end of prologue
	MOV.W	R12, 2(R1)
	MOV.W	R13, @R1
	MOV.W	#5381, 6(R1)
	MOV.W	#0, 8(R1)
	MOV.W	#0, 4(R1)
	BR	#.L2
.L3:
	MOV.W	6(R1), R12
	MOV.W	8(R1), R13
	CALL	#__mspabi_slll_5
	MOV.W	R12, R8
	ADD	6(R1), R8 ; cy
	MOV.W	8(R1), R9
	ADDC	R13, R9
	MOV.W	2(R1), R12
	MOV.B	@R12, R12
	CLR	R13
	MOV.W	R8, R14
	ADD	R12, R14 ; cy
	MOV.W	R14, 6(R1)
	MOV.W	R9, R14
	ADDC	R13, R14
	MOV.W	R14, 8(R1)
	ADD.W	#1, 2(R1)
	ADD.W	#1, 4(R1)
.L2:
	CMP.W	@R1, 4(R1) { JLO	.L3
	MOV.W	6(R1), R12
	; start of epilogue
	ADD.W	#10, R1
	POPM.W	#2, r9
	RET
	.size	djb_hash, .-djb_hash
	.balign 2
	.type	hash_fp_to_index, @function
hash_fp_to_index:
; start of function
; framesize_regs:     0
; framesize_locals:   4
; framesize_outgoing: 0
; framesize:          4
; elim ap -> fp       2
; elim fp -> sp       4
; saved regs:(none)
	; start of prologue
	SUB.W	#4, R1
	; end of prologue
	MOV.W	R12, @R1
	MOV.W	R1, R12
	MOV.B	#2, R13
	CALL	#djb_hash
	MOV.W	R12, 2(R1)
	MOV.W	2(R1), R12
	AND.B	#63, R12
	; start of epilogue
	ADD.W	#4, R1
	RET
	.size	hash_fp_to_index, .-hash_fp_to_index
	.balign 2
	.type	hash_key_to_index, @function
hash_key_to_index:
; start of function
; framesize_regs:     0
; framesize_locals:   4
; framesize_outgoing: 0
; framesize:          4
; elim ap -> fp       2
; elim fp -> sp       4
; saved regs:(none)
	; start of prologue
	SUB.W	#4, R1
	; end of prologue
	MOV.W	R12, @R1
	MOV.W	R1, R12
	MOV.B	#2, R13
	CALL	#djb_hash
	MOV.W	R12, 2(R1)
	MOV.W	2(R1), R12
	AND.B	#63, R12
	; start of epilogue
	ADD.W	#4, R1
	RET
	.size	hash_key_to_index, .-hash_key_to_index
	.balign 2
	.type	hash_to_fingerprint, @function
hash_to_fingerprint:
; start of function
; framesize_regs:     0
; framesize_locals:   2
; framesize_outgoing: 0
; framesize:          2
; elim ap -> fp       2
; elim fp -> sp       2
; saved regs:(none)
	; start of prologue
	SUB.W	#2, R1
	; end of prologue
	MOV.W	R12, @R1
	MOV.W	R1, R12
	MOV.B	#2, R13
	CALL	#djb_hash
	; start of epilogue
	ADD.W	#2, R1
	RET
	.size	hash_to_fingerprint, .-hash_to_fingerprint
	.balign 2
	.type	generate_key, @function
generate_key:
; start of function
; framesize_regs:     0
; framesize_locals:   2
; framesize_outgoing: 0
; framesize:          2
; elim ap -> fp       2
; elim fp -> sp       2
; saved regs:(none)
	; start of prologue
	SUB.W	#2, R1
	; end of prologue
	MOV.W	R12, @R1
	MOV.W	@R1, R13
	ADD.W	#1, R13
	MOV.W	R13, R12
	RLAM.W	#4, R12
	ADD.W	R13, R12
	; start of epilogue
	ADD.W	#2, R1
	RET
	.size	generate_key, .-generate_key
	.balign 2
	.type	insert, @function
insert:
; start of function
; framesize_regs:     0
; framesize_locals:   26
; framesize_outgoing: 0
; framesize:          26
; elim ap -> fp       2
; elim fp -> sp       26
; saved regs:(none)
	; start of prologue
	SUB.W	#26, R1
	; end of prologue
	MOV.W	R12, 2(R1)
	MOV.W	R13, @R1
	MOV.W	#0, 20(R1)
	MOV.W	@R1, R12
	CALL	#hash_to_fingerprint
	MOV.W	R12, 18(R1)
	MOV.W	@R1, R12
	CALL	#hash_key_to_index
	MOV.W	R12, 16(R1)
	MOV.W	18(R1), R12
	CALL	#hash_fp_to_index
	MOV.W	R12, 14(R1)
	MOV.W	16(R1), R12
	XOR.W	14(R1), R12
	MOV.W	R12, 12(R1)
	MOV.W	16(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	@R12, 10(R1)
	CMP.W	#0, 10(R1) { JNE	.L14
	MOV.W	16(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	18(R1), @R12
	BR	#.L15
.L14:
	MOV.W	12(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	@R12, 8(R1)
	CMP.W	#0, 8(R1) { JNE	.L16
	MOV.W	12(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	18(R1), @R12
	BR	#.L15
.L16:
	CALL	#rand
	AND.B	#128, R12
	CMP.W	#0, R12 { JEQ	.L17
	MOV.W	16(R1), 22(R1)
	MOV.W	10(R1), 24(R1)
	BR	#.L18
.L17:
	MOV.W	12(R1), 22(R1)
	MOV.W	8(R1), 24(R1)
.L18:
	MOV.W	22(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	18(R1), @R12
.L20:
	MOV.W	24(R1), R12
	CALL	#hash_fp_to_index
	MOV.W	R12, 6(R1)
	XOR.W	6(R1), 22(R1)
	MOV.W	22(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	@R12, 4(R1)
	MOV.W	22(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	24(R1), @R12
	MOV.W	4(R1), 24(R1)
	CMP.W	#0, 24(R1) { JEQ	.L19
	ADD.W	#1, 20(R1)
	MOV.B	#7, R12
	CMP.W	20(R1), R12 { JHS	.L20
.L19:
	CMP.W	#0, 24(R1) { JEQ	.L15
	MOV.B	#0, R12
	BR	#.L21
.L15:
	MOV.B	#1, R12
.L21:
	; start of epilogue
	ADD.W	#26, R1
	RET
	.size	insert, .-insert
	.balign 2
	.type	lookup, @function
lookup:
; start of function
; framesize_regs:     0
; framesize_locals:   12
; framesize_outgoing: 0
; framesize:          12
; elim ap -> fp       2
; elim fp -> sp       12
; saved regs:(none)
	; start of prologue
	SUB.W	#12, R1
	; end of prologue
	MOV.W	R12, 2(R1)
	MOV.W	R13, @R1
	MOV.W	@R1, R12
	CALL	#hash_to_fingerprint
	MOV.W	R12, 10(R1)
	MOV.W	@R1, R12
	CALL	#hash_key_to_index
	MOV.W	R12, 8(R1)
	MOV.W	10(R1), R12
	CALL	#hash_fp_to_index
	MOV.W	R12, 6(R1)
	MOV.W	8(R1), R12
	XOR.W	6(R1), R12
	MOV.W	R12, 4(R1)
	MOV.W	8(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	@R12, R12
	CMP.W	R12, 10(R1) { JEQ	.L23
	MOV.W	4(R1), R12
	RLAM.W	#1, R12
	ADD.W	2(R1), R12
	MOV.W	@R12, R12
	CMP.W	R12, 10(R1) { JNE	.L24
.L23:
	MOV.B	#1, R12
	BR	#.L25
.L24:
	MOV.B	#0, R12
.L25:
	AND.B	#1, R12
	AND	#0xff, R12
	; start of epilogue
	ADD.W	#12, R1
	RET
	.size	lookup, .-lookup
	.balign 2
	.global	init
	.type	init, @function
init:
; start of function
; framesize_regs:     0
; framesize_locals:   0
; framesize_outgoing: 0
; framesize:          0
; elim ap -> fp       2
; elim fp -> sp       0
; saved regs:(none)
	; start of prologue
	; end of prologue
	MOV.W	#23168, &WDTCTL
	MOV.W	&PM5CTL0, R12
	BIC.W	#1, R12
	MOV.W	R12, &PM5CTL0
	MOV.B	&P1DIR, R12
	BIS.B	#4, R12
	AND	#0xff, R12
	MOV.B	R12, &P1DIR
	MOV.B	&P1OUT, R12
	BIS.B	#4, R12
	AND	#0xff, R12
	MOV.B	R12, &P1OUT
	MOV.B	#-91, &CSCTL0_H
	MOV.W	#12, &CSCTL1
	MOV.W	#51, &CSCTL2
	MOV.W	#0, &CSCTL3
	MOV.W	#1, &UCA0CTLW0
	MOV.W	&UCA0CTLW0, R12
	BIS.W	#128, R12
	MOV.W	R12, &UCA0CTLW0
	MOV.B	#4, &UCA0BRW_L
	MOV.B	#0, &UCA0BRW_H
	MOV.W	#21825, &UCA0MCTLW
	MOV.B	&P2SEL1, R12
	BIS.B	#3, R12
	AND	#0xff, R12
	MOV.B	R12, &P2SEL1
	MOV.B	&P2SEL0, R12
	AND.B	#-4, R12
	AND	#0xff, R12
	MOV.B	R12, &P2SEL0
	MOV.W	&UCA0CTLW0, R12
	BIC.W	#1, R12
	MOV.W	R12, &UCA0CTLW0
	NOP
	; start of epilogue
	RET
	.size	init, .-init
	.balign 2
	.global	main
	.type	main, @function
main:
; start of function
; framesize_regs:     0
; framesize_locals:   142
; framesize_outgoing: 0
; framesize:          142
; elim ap -> fp       2
; elim fp -> sp       142
; saved regs:(none)
	; start of prologue
	SUB.W	#142, R1
	; end of prologue
	CALL	#init
	MOV.W	R1, R12
	MOV.B	#128, R14
	MOV.B	#0, R13
	CALL	#memset
	MOV.W	#1, 138(R1)
	MOV.W	#0, 136(R1)
	MOV.W	#0, 140(R1)
	BR	#.L29
.L31:
	MOV.W	138(R1), R12
	CALL	#generate_key
	MOV.W	R12, 138(R1)
	MOV.W	R1, R12
	MOV.W	138(R1), R13
	CALL	#insert
	MOV.B	R12, 129(R1)
	CMP.B	#0, 129(R1) { JEQ	.L30
	ADD.W	#1, 136(R1)
.L30:
	ADD.W	#1, 140(R1)
.L29:
	MOV.B	#15, R12
	CMP.W	140(R1), R12 { JHS	.L31
	MOV.W	#1, 138(R1)
	MOV.W	#0, 134(R1)
	MOV.W	#0, 140(R1)
	BR	#.L32
.L35:
	MOV.W	138(R1), R12
	CALL	#generate_key
	MOV.W	R12, 138(R1)
	MOV.W	R1, R12
	MOV.W	138(R1), R13
	CALL	#lookup
	MOV.B	R12, 133(R1)
	CMP.B	#0, 133(R1) { JEQ	.L33
	ADD.W	#1, 134(R1)
	BR	#.L34
.L33:
	MOV.W	138(R1), R12
	CALL	#hash_to_fingerprint
	MOV.W	R12, 130(R1)
.L34:
	ADD.W	#1, 140(R1)
.L32:
	MOV.B	#15, R12
	CMP.W	140(R1), R12 { JHS	.L35
	MOV.B	&P1OUT, R12
	BIC.B	#4, R12
	AND	#0xff, R12
	MOV.B	R12, &P1OUT
	MOV.B	#0, R12
	; start of epilogue
	.refsym	__crt0_call_exit
	ADD.W	#142, R1
	RET
	.size	main, .-main
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
