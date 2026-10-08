	.file	"test_global_v2.c"
.text
	.balign 2
	.global	compute_conv
	.type	compute_conv, @function
compute_conv:
; start of function
; framesize_regs:     14
; framesize_locals:   0
; framesize_outgoing: 0
; framesize:          14
; elim ap -> fp       16
; elim fp -> sp       0
; saved regs: R4 R5 R6 R7 R8 R9 R10
	; start of prologue
	PUSHM.W	#7, R10
	; end of prologue
	MOV.W	#vec, R4
	MOV.W	R4, R13
	MOV.B	#0, R12
.L2:
	MOV.W	R12, @R13
	ADD.W	#2, R13
	ADD.W	#1, R12
	CMP.W	#50, R12 { JNE	.L2
	MOV.W	#out, R5
	MOV.W	#out+92, R13
	MOV.W	R5, R12
.L3:
	MOV.W	#0, @R12
	ADD.W	#2, R12
	CMP.W	R13, R12 { JNE	.L3
	MOV.B	#0, R6
	MOV.W	#kernel-10, R7
	BR	#.L4
.L10:
	MOV.W	R9, -2(R5)
	ADD.W	#1, R6
	ADD.W	#2, R4
	CMP.W	#46, R6 { JEQ	.L6
.L4:
	MOV.W	@R5+, R9
	MOV.W	#kernel, R10
	MOV.W	R4, R8
.L5:
	MOV.W	@R8+, R12
	MOV.W	8(R10), R13
	CALL	#__mspabi_mpyi_f5hw
	ADD.W	R12, R9
	ADD.W	#-2, R10
	CMP.W	R7, R10 { JNE	.L5
	BR	#.L10
.L6:
	MOV.W	&out, R12
	; start of epilogue
	POPM.W	#7, r10
	RET
	.size	compute_conv, .-compute_conv
	.global	out
	.section .bss
	.balign 2
	.type	out, @object
	.size	out, 92
out:
	.zero	92
	.global	kernel
	.section	.rodata
	.balign 2
	.type	kernel, @object
	.size	kernel, 10
kernel:
	.short	1
	.short	1
	.short	1
	.short	1
	.short	1
	.global	vec
	.section .bss
	.balign 2
	.type	vec, @object
	.size	vec, 100
vec:
	.zero	100
	.ident	"GCC: (GNU) 9.3.1"
	.mspabi_attribute 4, 2
	.mspabi_attribute 6, 1
	.mspabi_attribute 8, 1
	.gnu_attribute 4, 1
