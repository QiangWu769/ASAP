; ================================================
; ASAP 恢复逻辑 - 表驱动实现（去重优化版）
; 自动生成 - 请勿手动编辑
; 总 WID: 148, 唯一恢复列表: 6
; 去重率: 95.9%
; ================================================

    .global _asap_restore
    .extern ASAP_WID_SAVE
    .extern ASAP_SP_SAVE
    .extern ASAP_PC_SAVE
    .extern __SLOT_REG_R12
    .extern __SLOT_REG_R13
    .extern __SLOT_REG_R14

    .comm __asap_restored_flag, 2, 2  ; 恢复标志（SRAM BSS，2字节）

    .section .rodata
    .align 2

; 唯一恢复列表（去重后）：每个恢复列表只生成一次
; 恢复列表 #1: 4 项, 被 1 个 WID 共享
; 共享 WID: W001
_unique_restore_list_1:
    .word 0xFFF8  ; 栈变量(MOV.B): _uart_putc::SP+1
    .word 0  ; SP调整量
    .word __SLOT__uart_putc_SP_1  ; FRAM地址
    .word 1  ; 栈偏移
    .word 4  ; SP调整量: _uart_puts::SP+0
    .word __SLOT__uart_puts_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 8  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; SP调整量（_uart_putc返回地址）
    .word RET_ADDR__UART_PUTC  ; 返回地址FRAM地址
    .word 2  ; 返回地址栈偏移
    .word 4  ; SP调整量（_uart_puts返回地址）
    .word RET_ADDR__UART_PUTS  ; 返回地址FRAM地址
    .word 2  ; 返回地址栈偏移
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; 恢复列表 #2: 3 项, 被 2 个 WID 共享
; 共享 WID: W002, W003
_unique_restore_list_2:
    .word 0  ; SP调整量: _uart_puts::SP+0
    .word __SLOT__uart_puts_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 4  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; SP调整量（_uart_puts返回地址）
    .word RET_ADDR__UART_PUTS  ; 返回地址FRAM地址
    .word 2  ; 返回地址栈偏移
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; 恢复列表 #3: 34 项, 被 5 个 WID 共享
; 共享 WID: W004, W005, W006, W007, W008
_unique_restore_list_3:
    .word 0  ; SP调整量: f_mul::SP+2
    .word __SLOT_f_mul_SP_2  ; FRAM地址
    .word 2  ; 栈偏移
    .word 0  ; SP调整量: f_mul::SP+0
    .word __SLOT_f_mul_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0  ; SP调整量: f_mul::SP+4
    .word __SLOT_f_mul_SP_4  ; FRAM地址
    .word 4  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+0
    .word __SLOT_dnn_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+52
    .word __SLOT_dnn_main_SP_52  ; FRAM地址
    .word 52  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+12
    .word __SLOT_dnn_main_SP_12  ; FRAM地址
    .word 12  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+46
    .word __SLOT_dnn_main_SP_46  ; FRAM地址
    .word 46  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R13+0
    .word __SLOT_dnn_main_R13_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R13_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 8  ; SP调整量: dnn_main::SP+2
    .word __SLOT_dnn_main_SP_2  ; FRAM地址
    .word 2  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R12+0
    .word __SLOT_dnn_main_R12_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R12_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 8  ; SP调整量: dnn_main::SP+42
    .word __SLOT_dnn_main_SP_42  ; FRAM地址
    .word 42  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+40
    .word __SLOT_dnn_main_SP_40  ; FRAM地址
    .word 40  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+50
    .word __SLOT_dnn_main_SP_50  ; FRAM地址
    .word 50  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+48
    .word __SLOT_dnn_main_SP_48  ; FRAM地址
    .word 48  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+6
    .word __SLOT_dnn_main_SP_6  ; FRAM地址
    .word 6  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+4
    .word __SLOT_dnn_main_SP_4  ; FRAM地址
    .word 4  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+38
    .word __SLOT_dnn_main_SP_38  ; FRAM地址
    .word 38  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+36
    .word __SLOT_dnn_main_SP_36  ; FRAM地址
    .word 36  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+10
    .word __SLOT_dnn_main_SP_10  ; FRAM地址
    .word 10  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+8
    .word __SLOT_dnn_main_SP_8  ; FRAM地址
    .word 8  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+44
    .word __SLOT_dnn_main_SP_44  ; FRAM地址
    .word 44  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+16
    .word __SLOT_dnn_main_SP_16  ; FRAM地址
    .word 16  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+14
    .word __SLOT_dnn_main_SP_14  ; FRAM地址
    .word 14  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+34
    .word __SLOT_dnn_main_SP_34  ; FRAM地址
    .word 34  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+32
    .word __SLOT_dnn_main_SP_32  ; FRAM地址
    .word 32  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+30
    .word __SLOT_dnn_main_SP_30  ; FRAM地址
    .word 30  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+28
    .word __SLOT_dnn_main_SP_28  ; FRAM地址
    .word 28  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+20
    .word __SLOT_dnn_main_SP_20  ; FRAM地址
    .word 20  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+18
    .word __SLOT_dnn_main_SP_18  ; FRAM地址
    .word 18  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+26
    .word __SLOT_dnn_main_SP_26  ; FRAM地址
    .word 26  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+24
    .word __SLOT_dnn_main_SP_24  ; FRAM地址
    .word 24  ; 栈偏移
    .word 8  ; SP调整量: dnn_main::SP+22
    .word __SLOT_dnn_main_SP_22  ; FRAM地址
    .word 22  ; 栈偏移
    .word 66  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; SP调整量（f_mul返回地址）
    .word RET_ADDR_F_MUL  ; 返回地址FRAM地址
    .word 6  ; 返回地址栈偏移
    .word 8  ; SP调整量（dnn_main返回地址）
    .word RET_ADDR_DNN_MAIN  ; 返回地址FRAM地址
    .word 56  ; 返回地址栈偏移
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; 恢复列表 #4: 37 项, 被 9 个 WID 共享
; 共享 WID: W009, W010, W011, W012, W013, W014, W015, W016, W017
_unique_restore_list_4:
    .word 0  ; SP调整量: my_memcpy::SP+4
    .word __SLOT_my_memcpy_SP_4  ; FRAM地址
    .word 4  ; 栈偏移
    .word 0  ; SP调整量: my_memcpy::SP+2
    .word __SLOT_my_memcpy_SP_2  ; FRAM地址
    .word 2  ; 栈偏移
    .word 0  ; SP调整量: my_memcpy::SP+0
    .word __SLOT_my_memcpy_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0  ; SP调整量: my_memcpy::SP+8
    .word __SLOT_my_memcpy_SP_8  ; FRAM地址
    .word 8  ; 栈偏移
    .word 0  ; SP调整量: my_memcpy::SP+6
    .word __SLOT_my_memcpy_SP_6  ; FRAM地址
    .word 6  ; 栈偏移
    .word 0xFFFD  ; 重定向间接寻址: my_memcpy::R12+0 → dnn_main::SP+0
    .word __SLOT_dnn_main_SP_0  ; 值的FRAM地址
    .word 12  ; 目标函数SP调整
    .word 0  ; 目标栈偏移
    .word 0  ; 间接偏移
    .word 0  ; 寄存器编号（保留）
    .word 12  ; SP调整量: dnn_main::SP+52
    .word __SLOT_dnn_main_SP_52  ; FRAM地址
    .word 52  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+12
    .word __SLOT_dnn_main_SP_12  ; FRAM地址
    .word 12  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+46
    .word __SLOT_dnn_main_SP_46  ; FRAM地址
    .word 46  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R13+0
    .word __SLOT_dnn_main_R13_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R13_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 12  ; SP调整量: dnn_main::SP+2
    .word __SLOT_dnn_main_SP_2  ; FRAM地址
    .word 2  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R12+0
    .word __SLOT_dnn_main_R12_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R12_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 12  ; SP调整量: dnn_main::SP+42
    .word __SLOT_dnn_main_SP_42  ; FRAM地址
    .word 42  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+40
    .word __SLOT_dnn_main_SP_40  ; FRAM地址
    .word 40  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+50
    .word __SLOT_dnn_main_SP_50  ; FRAM地址
    .word 50  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+48
    .word __SLOT_dnn_main_SP_48  ; FRAM地址
    .word 48  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+6
    .word __SLOT_dnn_main_SP_6  ; FRAM地址
    .word 6  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+4
    .word __SLOT_dnn_main_SP_4  ; FRAM地址
    .word 4  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+38
    .word __SLOT_dnn_main_SP_38  ; FRAM地址
    .word 38  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+36
    .word __SLOT_dnn_main_SP_36  ; FRAM地址
    .word 36  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+10
    .word __SLOT_dnn_main_SP_10  ; FRAM地址
    .word 10  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+8
    .word __SLOT_dnn_main_SP_8  ; FRAM地址
    .word 8  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+44
    .word __SLOT_dnn_main_SP_44  ; FRAM地址
    .word 44  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+16
    .word __SLOT_dnn_main_SP_16  ; FRAM地址
    .word 16  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+14
    .word __SLOT_dnn_main_SP_14  ; FRAM地址
    .word 14  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+34
    .word __SLOT_dnn_main_SP_34  ; FRAM地址
    .word 34  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+32
    .word __SLOT_dnn_main_SP_32  ; FRAM地址
    .word 32  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+30
    .word __SLOT_dnn_main_SP_30  ; FRAM地址
    .word 30  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+28
    .word __SLOT_dnn_main_SP_28  ; FRAM地址
    .word 28  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+20
    .word __SLOT_dnn_main_SP_20  ; FRAM地址
    .word 20  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+18
    .word __SLOT_dnn_main_SP_18  ; FRAM地址
    .word 18  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+26
    .word __SLOT_dnn_main_SP_26  ; FRAM地址
    .word 26  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+24
    .word __SLOT_dnn_main_SP_24  ; FRAM地址
    .word 24  ; 栈偏移
    .word 12  ; SP调整量: dnn_main::SP+22
    .word __SLOT_dnn_main_SP_22  ; FRAM地址
    .word 22  ; 栈偏移
    .word 70  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; SP调整量（my_memcpy返回地址）
    .word RET_ADDR_MY_MEMCPY  ; 返回地址FRAM地址
    .word 10  ; 返回地址栈偏移
    .word 12  ; SP调整量（dnn_main返回地址）
    .word RET_ADDR_DNN_MAIN  ; 返回地址FRAM地址
    .word 56  ; 返回地址栈偏移
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; 恢复列表 #5: 31 项, 被 128 个 WID 共享
; 共享 WID: W018, W019, W020, W021, W022, W023, W024, W025, W026, W027, W028, W029, W030, W031, W032, W033, W034, W035, W036, W037, W038, W039, W040, W041, W042, W043, W044, W045, W046, W047, W048, W049, W050, W051, W052, W053, W054, W055, W056, W057, W058, W059, W060, W061, W062, W063, W064, W065, W066, W067, W068, W069, W070, W071, W072, W073, W074, W075, W076, W077, W078, W079, W080, W081, W082, W083, W084, W085, W086, W087, W088, W089, W090, W091, W092, W093, W094, W095, W096, W097, W098, W099, W100, W101, W102, W103, W104, W105, W106, W107, W108, W109, W110, W111, W112, W113, W114, W115, W116, W117, W118, W119, W120, W121, W122, W123, W124, W125, W126, W127, W128, W129, W130, W131, W132, W133, W134, W135, W136, W137, W138, W139, W140, W141, W142, W143, W144, W145
_unique_restore_list_5:
    .word 0  ; SP调整量: dnn_main::SP+0
    .word __SLOT_dnn_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+52
    .word __SLOT_dnn_main_SP_52  ; FRAM地址
    .word 52  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+12
    .word __SLOT_dnn_main_SP_12  ; FRAM地址
    .word 12  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+46
    .word __SLOT_dnn_main_SP_46  ; FRAM地址
    .word 46  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R13+0
    .word __SLOT_dnn_main_R13_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R13_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 0  ; SP调整量: dnn_main::SP+2
    .word __SLOT_dnn_main_SP_2  ; FRAM地址
    .word 2  ; 栈偏移
    .word 0xFFFE  ; 间接寻址恢复(MOV.W): dnn_main::R12+0
    .word __SLOT_dnn_main_R12_0  ; 值的FRAM地址
    .word __ADDR_dnn_main_R12_0  ; 基地址的FRAM地址
    .word 0  ; 偏移量
    .word 0  ; SP调整量: dnn_main::SP+42
    .word __SLOT_dnn_main_SP_42  ; FRAM地址
    .word 42  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+40
    .word __SLOT_dnn_main_SP_40  ; FRAM地址
    .word 40  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+50
    .word __SLOT_dnn_main_SP_50  ; FRAM地址
    .word 50  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+48
    .word __SLOT_dnn_main_SP_48  ; FRAM地址
    .word 48  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+6
    .word __SLOT_dnn_main_SP_6  ; FRAM地址
    .word 6  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+4
    .word __SLOT_dnn_main_SP_4  ; FRAM地址
    .word 4  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+38
    .word __SLOT_dnn_main_SP_38  ; FRAM地址
    .word 38  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+36
    .word __SLOT_dnn_main_SP_36  ; FRAM地址
    .word 36  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+10
    .word __SLOT_dnn_main_SP_10  ; FRAM地址
    .word 10  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+8
    .word __SLOT_dnn_main_SP_8  ; FRAM地址
    .word 8  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+44
    .word __SLOT_dnn_main_SP_44  ; FRAM地址
    .word 44  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+16
    .word __SLOT_dnn_main_SP_16  ; FRAM地址
    .word 16  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+14
    .word __SLOT_dnn_main_SP_14  ; FRAM地址
    .word 14  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+34
    .word __SLOT_dnn_main_SP_34  ; FRAM地址
    .word 34  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+32
    .word __SLOT_dnn_main_SP_32  ; FRAM地址
    .word 32  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+30
    .word __SLOT_dnn_main_SP_30  ; FRAM地址
    .word 30  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+28
    .word __SLOT_dnn_main_SP_28  ; FRAM地址
    .word 28  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+20
    .word __SLOT_dnn_main_SP_20  ; FRAM地址
    .word 20  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+18
    .word __SLOT_dnn_main_SP_18  ; FRAM地址
    .word 18  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+26
    .word __SLOT_dnn_main_SP_26  ; FRAM地址
    .word 26  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+24
    .word __SLOT_dnn_main_SP_24  ; FRAM地址
    .word 24  ; 栈偏移
    .word 0  ; SP调整量: dnn_main::SP+22
    .word __SLOT_dnn_main_SP_22  ; FRAM地址
    .word 22  ; 栈偏移
    .word 58  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; SP调整量（dnn_main返回地址）
    .word RET_ADDR_DNN_MAIN  ; 返回地址FRAM地址
    .word 56  ; 返回地址栈偏移
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; 恢复列表 #6: 2 项, 被 3 个 WID 共享
; 共享 WID: W146, W147, W148
_unique_restore_list_6:
    .word 0  ; SP调整量: main::SP+0
    .word __SLOT_main_SP_0  ; FRAM地址
    .word 0  ; 栈偏移
    .word 0xFFFB  ; SRAM全局变量: SRAM::count
    .word __SLOT_SRAM_count  ; 值的FRAM地址
    .word count  ; SRAM目标地址
    .word 0xFFFF  ; 返回地址标记
    .word 0  ; 返回地址结束标记
    .word 0  ; FRAM地址=0表示没有更多返回地址
    .word 0  ; 占位符
    .word 0  ; PC 占位符（在跳转表中指定）
    .word 0  ; 结束标记

; WID 跳转表：每个 WID 包含 [恢复列表指针, PC]
_restore_table:
    .word _unique_restore_list_1  ; W001 → 列表 #1
    .word 0x9D24  ; W001 的恢复 PC
    .word _unique_restore_list_2  ; W002 → 列表 #2
    .word 0x9D5A  ; W002 的恢复 PC
    .word _unique_restore_list_2  ; W003 → 列表 #2
    .word 0x9D78  ; W003 的恢复 PC
    .word _unique_restore_list_3  ; W004 → 列表 #3
    .word 0x9DAE  ; W004 的恢复 PC
    .word _unique_restore_list_3  ; W005 → 列表 #3
    .word 0x9DC0  ; W005 的恢复 PC
    .word _unique_restore_list_3  ; W006 → 列表 #3
    .word 0x9DDA  ; W006 的恢复 PC
    .word _unique_restore_list_3  ; W007 → 列表 #3
    .word 0x9DDA  ; W007 的恢复 PC
    .word _unique_restore_list_3  ; W008 → 列表 #3
    .word 0x9E02  ; W008 的恢复 PC
    .word _unique_restore_list_4  ; W009 → 列表 #4
    .word 0x9E2E  ; W009 的恢复 PC
    .word _unique_restore_list_4  ; W010 → 列表 #4
    .word 0x9E42  ; W010 的恢复 PC
    .word _unique_restore_list_4  ; W011 → 列表 #4
    .word 0x9E54  ; W011 的恢复 PC
    .word _unique_restore_list_4  ; W012 → 列表 #4
    .word 0x9E66  ; W012 的恢复 PC
    .word _unique_restore_list_4  ; W013 → 列表 #4
    .word 0x9E78  ; W013 的恢复 PC
    .word _unique_restore_list_4  ; W014 → 列表 #4
    .word 0x9E92  ; W014 的恢复 PC
    .word _unique_restore_list_4  ; W015 → 列表 #4
    .word 0x9EAE  ; W015 的恢复 PC
    .word _unique_restore_list_4  ; W016 → 列表 #4
    .word 0x9EC2  ; W016 的恢复 PC
    .word _unique_restore_list_4  ; W017 → 列表 #4
    .word 0x9EDA  ; W017 的恢复 PC
    .word _unique_restore_list_5  ; W018 → 列表 #5
    .word 0x9F9A  ; W018 的恢复 PC
    .word _unique_restore_list_5  ; W019 → 列表 #5
    .word 0x9FBA  ; W019 的恢复 PC
    .word _unique_restore_list_5  ; W020 → 列表 #5
    .word 0x9FD6  ; W020 的恢复 PC
    .word _unique_restore_list_5  ; W021 → 列表 #5
    .word 0x9FE6  ; W021 的恢复 PC
    .word _unique_restore_list_5  ; W022 → 列表 #5
    .word 0xA02E  ; W022 的恢复 PC
    .word _unique_restore_list_5  ; W023 → 列表 #5
    .word 0xA046  ; W023 的恢复 PC
    .word _unique_restore_list_5  ; W024 → 列表 #5
    .word 0xA068  ; W024 的恢复 PC
    .word _unique_restore_list_5  ; W025 → 列表 #5
    .word 0xA080  ; W025 的恢复 PC
    .word _unique_restore_list_5  ; W026 → 列表 #5
    .word 0xA0A2  ; W026 的恢复 PC
    .word _unique_restore_list_5  ; W027 → 列表 #5
    .word 0xA0CC  ; W027 的恢复 PC
    .word _unique_restore_list_5  ; W028 → 列表 #5
    .word 0xA0DC  ; W028 的恢复 PC
    .word _unique_restore_list_5  ; W029 → 列表 #5
    .word 0xA0FC  ; W029 的恢复 PC
    .word _unique_restore_list_5  ; W030 → 列表 #5
    .word 0xA114  ; W030 的恢复 PC
    .word _unique_restore_list_5  ; W031 → 列表 #5
    .word 0xA12E  ; W031 的恢复 PC
    .word _unique_restore_list_5  ; W032 → 列表 #5
    .word 0xA154  ; W032 的恢复 PC
    .word _unique_restore_list_5  ; W033 → 列表 #5
    .word 0xA164  ; W033 的恢复 PC
    .word _unique_restore_list_5  ; W034 → 列表 #5
    .word 0xA174  ; W034 的恢复 PC
    .word _unique_restore_list_5  ; W035 → 列表 #5
    .word 0xA186  ; W035 的恢复 PC
    .word _unique_restore_list_5  ; W036 → 列表 #5
    .word 0xA1E2  ; W036 的恢复 PC
    .word _unique_restore_list_5  ; W037 → 列表 #5
    .word 0xA1FA  ; W037 的恢复 PC
    .word _unique_restore_list_5  ; W038 → 列表 #5
    .word 0xA212  ; W038 的恢复 PC
    .word _unique_restore_list_5  ; W039 → 列表 #5
    .word 0xA234  ; W039 的恢复 PC
    .word _unique_restore_list_5  ; W040 → 列表 #5
    .word 0xA256  ; W040 的恢复 PC
    .word _unique_restore_list_5  ; W041 → 列表 #5
    .word 0xA276  ; W041 的恢复 PC
    .word _unique_restore_list_5  ; W042 → 列表 #5
    .word 0xA28E  ; W042 的恢复 PC
    .word _unique_restore_list_5  ; W043 → 列表 #5
    .word 0xA2B8  ; W043 的恢复 PC
    .word _unique_restore_list_5  ; W044 → 列表 #5
    .word 0xA2DE  ; W044 的恢复 PC
    .word _unique_restore_list_5  ; W045 → 列表 #5
    .word 0xA2EE  ; W045 的恢复 PC
    .word _unique_restore_list_5  ; W046 → 列表 #5
    .word 0xA316  ; W046 的恢复 PC
    .word _unique_restore_list_5  ; W047 → 列表 #5
    .word 0xA32E  ; W047 的恢复 PC
    .word _unique_restore_list_5  ; W048 → 列表 #5
    .word 0xA348  ; W048 的恢复 PC
    .word _unique_restore_list_5  ; W049 → 列表 #5
    .word 0xA36E  ; W049 的恢复 PC
    .word _unique_restore_list_5  ; W050 → 列表 #5
    .word 0xA37E  ; W050 的恢复 PC
    .word _unique_restore_list_5  ; W051 → 列表 #5
    .word 0xA38E  ; W051 的恢复 PC
    .word _unique_restore_list_5  ; W052 → 列表 #5
    .word 0xA3A0  ; W052 的恢复 PC
    .word _unique_restore_list_5  ; W053 → 列表 #5
    .word 0xA400  ; W053 的恢复 PC
    .word _unique_restore_list_5  ; W054 → 列表 #5
    .word 0xA418  ; W054 的恢复 PC
    .word _unique_restore_list_5  ; W055 → 列表 #5
    .word 0xA430  ; W055 的恢复 PC
    .word _unique_restore_list_5  ; W056 → 列表 #5
    .word 0xA452  ; W056 的恢复 PC
    .word _unique_restore_list_5  ; W057 → 列表 #5
    .word 0xA474  ; W057 的恢复 PC
    .word _unique_restore_list_5  ; W058 → 列表 #5
    .word 0xA496  ; W058 的恢复 PC
    .word _unique_restore_list_5  ; W059 → 列表 #5
    .word 0xA4A6  ; W059 的恢复 PC
    .word _unique_restore_list_5  ; W060 → 列表 #5
    .word 0xA4DC  ; W060 的恢复 PC
    .word _unique_restore_list_5  ; W061 → 列表 #5
    .word 0xA4F4  ; W061 的恢复 PC
    .word _unique_restore_list_5  ; W062 → 列表 #5
    .word 0xA516  ; W062 的恢复 PC
    .word _unique_restore_list_5  ; W063 → 列表 #5
    .word 0xA52E  ; W063 的恢复 PC
    .word _unique_restore_list_5  ; W064 → 列表 #5
    .word 0xA564  ; W064 的恢复 PC
    .word _unique_restore_list_5  ; W065 → 列表 #5
    .word 0xA57C  ; W065 的恢复 PC
    .word _unique_restore_list_5  ; W066 → 列表 #5
    .word 0xA596  ; W066 的恢复 PC
    .word _unique_restore_list_5  ; W067 → 列表 #5
    .word 0xA5BE  ; W067 的恢复 PC
    .word _unique_restore_list_5  ; W068 → 列表 #5
    .word 0xA5DA  ; W068 的恢复 PC
    .word _unique_restore_list_5  ; W069 → 列表 #5
    .word 0xA5EA  ; W069 的恢复 PC
    .word _unique_restore_list_5  ; W070 → 列表 #5
    .word 0xA5FC  ; W070 的恢复 PC
    .word _unique_restore_list_5  ; W071 → 列表 #5
    .word 0xA628  ; W071 的恢复 PC
    .word _unique_restore_list_5  ; W072 → 列表 #5
    .word 0xA654  ; W072 的恢复 PC
    .word _unique_restore_list_5  ; W073 → 列表 #5
    .word 0xA66E  ; W073 的恢复 PC
    .word _unique_restore_list_5  ; W074 → 列表 #5
    .word 0xA69A  ; W074 的恢复 PC
    .word _unique_restore_list_5  ; W075 → 列表 #5
    .word 0xA6B4  ; W075 的恢复 PC
    .word _unique_restore_list_5  ; W076 → 列表 #5
    .word 0xA6E2  ; W076 的恢复 PC
    .word _unique_restore_list_5  ; W077 → 列表 #5
    .word 0xA6FC  ; W077 的恢复 PC
    .word _unique_restore_list_5  ; W078 → 列表 #5
    .word 0xA738  ; W078 的恢复 PC
    .word _unique_restore_list_5  ; W079 → 列表 #5
    .word 0xA744  ; W079 的恢复 PC
    .word _unique_restore_list_5  ; W080 → 列表 #5
    .word 0xA75E  ; W080 的恢复 PC
    .word _unique_restore_list_5  ; W081 → 列表 #5
    .word 0xA780  ; W081 的恢复 PC
    .word _unique_restore_list_5  ; W082 → 列表 #5
    .word 0xA798  ; W082 的恢复 PC
    .word _unique_restore_list_5  ; W083 → 列表 #5
    .word 0xA7BA  ; W083 的恢复 PC
    .word _unique_restore_list_5  ; W084 → 列表 #5
    .word 0xA7CA  ; W084 的恢复 PC
    .word _unique_restore_list_5  ; W085 → 列表 #5
    .word 0xA7F2  ; W085 的恢复 PC
    .word _unique_restore_list_5  ; W086 → 列表 #5
    .word 0xA80A  ; W086 的恢复 PC
    .word _unique_restore_list_5  ; W087 → 列表 #5
    .word 0xA824  ; W087 的恢复 PC
    .word _unique_restore_list_5  ; W088 → 列表 #5
    .word 0xA836  ; W088 的恢复 PC
    .word _unique_restore_list_5  ; W089 → 列表 #5
    .word 0xA848  ; W089 的恢复 PC
    .word _unique_restore_list_5  ; W090 → 列表 #5
    .word 0xA892  ; W090 的恢复 PC
    .word _unique_restore_list_5  ; W091 → 列表 #5
    .word 0xA8A2  ; W091 的恢复 PC
    .word _unique_restore_list_5  ; W092 → 列表 #5
    .word 0xA8B2  ; W092 的恢复 PC
    .word _unique_restore_list_5  ; W093 → 列表 #5
    .word 0xA8C4  ; W093 的恢复 PC
    .word _unique_restore_list_5  ; W094 → 列表 #5
    .word 0xA934  ; W094 的恢复 PC
    .word _unique_restore_list_5  ; W095 → 列表 #5
    .word 0xA94C  ; W095 的恢复 PC
    .word _unique_restore_list_5  ; W096 → 列表 #5
    .word 0xA964  ; W096 的恢复 PC
    .word _unique_restore_list_5  ; W097 → 列表 #5
    .word 0xA986  ; W097 的恢复 PC
    .word _unique_restore_list_5  ; W098 → 列表 #5
    .word 0xA9A8  ; W098 的恢复 PC
    .word _unique_restore_list_5  ; W099 → 列表 #5
    .word 0xA9C8  ; W099 的恢复 PC
    .word _unique_restore_list_5  ; W100 → 列表 #5
    .word 0xA9E8  ; W100 的恢复 PC
    .word _unique_restore_list_5  ; W101 → 列表 #5
    .word 0xAA0A  ; W101 的恢复 PC
    .word _unique_restore_list_5  ; W102 → 列表 #5
    .word 0xAA1A  ; W102 的恢复 PC
    .word _unique_restore_list_5  ; W103 → 列表 #5
    .word 0xAA50  ; W103 的恢复 PC
    .word _unique_restore_list_5  ; W104 → 列表 #5
    .word 0xAA68  ; W104 的恢复 PC
    .word _unique_restore_list_5  ; W105 → 列表 #5
    .word 0xAA8A  ; W105 的恢复 PC
    .word _unique_restore_list_5  ; W106 → 列表 #5
    .word 0xAAA4  ; W106 的恢复 PC
    .word _unique_restore_list_5  ; W107 → 列表 #5
    .word 0xAADA  ; W107 的恢复 PC
    .word _unique_restore_list_5  ; W108 → 列表 #5
    .word 0xAAF2  ; W108 的恢复 PC
    .word _unique_restore_list_5  ; W109 → 列表 #5
    .word 0xAB0C  ; W109 的恢复 PC
    .word _unique_restore_list_5  ; W110 → 列表 #5
    .word 0xAB2E  ; W110 的恢复 PC
    .word _unique_restore_list_5  ; W111 → 列表 #5
    .word 0xAB44  ; W111 的恢复 PC
    .word _unique_restore_list_5  ; W112 → 列表 #5
    .word 0xAB54  ; W112 的恢复 PC
    .word _unique_restore_list_5  ; W113 → 列表 #5
    .word 0xAB66  ; W113 的恢复 PC
    .word _unique_restore_list_5  ; W114 → 列表 #5
    .word 0xAB8C  ; W114 的恢复 PC
    .word _unique_restore_list_5  ; W115 → 列表 #5
    .word 0xABB2  ; W115 的恢复 PC
    .word _unique_restore_list_5  ; W116 → 列表 #5
    .word 0xABCC  ; W116 的恢复 PC
    .word _unique_restore_list_5  ; W117 → 列表 #5
    .word 0xABF2  ; W117 的恢复 PC
    .word _unique_restore_list_5  ; W118 → 列表 #5
    .word 0xAC0C  ; W118 的恢复 PC
    .word _unique_restore_list_5  ; W119 → 列表 #5
    .word 0xAC34  ; W119 的恢复 PC
    .word _unique_restore_list_5  ; W120 → 列表 #5
    .word 0xAC4E  ; W120 的恢复 PC
    .word _unique_restore_list_5  ; W121 → 列表 #5
    .word 0xAC82  ; W121 的恢复 PC
    .word _unique_restore_list_5  ; W122 → 列表 #5
    .word 0xAC8E  ; W122 的恢复 PC
    .word _unique_restore_list_5  ; W123 → 列表 #5
    .word 0xACA8  ; W123 的恢复 PC
    .word _unique_restore_list_5  ; W124 → 列表 #5
    .word 0xACCA  ; W124 的恢复 PC
    .word _unique_restore_list_5  ; W125 → 列表 #5
    .word 0xACE4  ; W125 的恢复 PC
    .word _unique_restore_list_5  ; W126 → 列表 #5
    .word 0xAD14  ; W126 的恢复 PC
    .word _unique_restore_list_5  ; W127 → 列表 #5
    .word 0xAD24  ; W127 的恢复 PC
    .word _unique_restore_list_5  ; W128 → 列表 #5
    .word 0xAD7C  ; W128 的恢复 PC
    .word _unique_restore_list_5  ; W129 → 列表 #5
    .word 0xAD94  ; W129 的恢复 PC
    .word _unique_restore_list_5  ; W130 → 列表 #5
    .word 0xADB6  ; W130 的恢复 PC
    .word _unique_restore_list_5  ; W131 → 列表 #5
    .word 0xADD0  ; W131 的恢复 PC
    .word _unique_restore_list_5  ; W132 → 列表 #5
    .word 0xAE06  ; W132 的恢复 PC
    .word _unique_restore_list_5  ; W133 → 列表 #5
    .word 0xAE1E  ; W133 的恢复 PC
    .word _unique_restore_list_5  ; W134 → 列表 #5
    .word 0xAE38  ; W134 的恢复 PC
    .word _unique_restore_list_5  ; W135 → 列表 #5
    .word 0xAE68  ; W135 的恢复 PC
    .word _unique_restore_list_5  ; W136 → 列表 #5
    .word 0xAE78  ; W136 的恢复 PC
    .word _unique_restore_list_5  ; W137 → 列表 #5
    .word 0xAEC6  ; W137 的恢复 PC
    .word _unique_restore_list_5  ; W138 → 列表 #5
    .word 0xAEDE  ; W138 的恢复 PC
    .word _unique_restore_list_5  ; W139 → 列表 #5
    .word 0xAF00  ; W139 的恢复 PC
    .word _unique_restore_list_5  ; W140 → 列表 #5
    .word 0xAF1A  ; W140 的恢复 PC
    .word _unique_restore_list_5  ; W141 → 列表 #5
    .word 0xAF2A  ; W141 的恢复 PC
    .word _unique_restore_list_5  ; W142 → 列表 #5
    .word 0xAF3A  ; W142 的恢复 PC
    .word _unique_restore_list_5  ; W143 → 列表 #5
    .word 0xAF60  ; W143 的恢复 PC
    .word _unique_restore_list_5  ; W144 → 列表 #5
    .word 0xAF7A  ; W144 的恢复 PC
    .word _unique_restore_list_5  ; W145 → 列表 #5
    .word 0xAF92  ; W145 的恢复 PC
    .word _unique_restore_list_6  ; W146 → 列表 #6
    .word 0xAFEA  ; W146 的恢复 PC
    .word _unique_restore_list_6  ; W147 → 列表 #6
    .word 0xB044  ; W147 的恢复 PC
    .word _unique_restore_list_6  ; W148 → 列表 #6
    .word 0xB044  ; W148 的恢复 PC

    .section .text
    .align 2

_asap_restore:
    ; 从FRAM读取WID
    MOV.W &ASAP_WID_SAVE, R12
    ; 检查WID有效性
    CMP.W #0, R12
    JEQ _restore_end           ; WID=0 → 放弃
    CMP.W #149, R12
    JGE _restore_end           ; WID超范围 → 放弃

    ; 查表：R14 = 恢复列表指针, R15 = PC
    DEC.W R12                  ; R12 = WID-1
    RLA.W R12                  ; R12 = (WID-1)*2
    RLA.W R12                  ; R12 = (WID-1)*4 (每项4字节)
    ADD.W #_restore_table, R12 ; R12 = table地址
    MOV.W @R12+, R14           ; R14 = 恢复表指针
    MOV.W @R12, R15            ; R15 = 恢复PC
    MOV.W R15, &ASAP_PC_SAVE   ; 保存PC到FRAM

_restore_items:
    ; 恢复循环：支持 MOV.B/MOV.W 区分
    ; 标记: 0xFFFF=结束, 0xFFFE=间接(W), 0xFFF9=间接(B), 0xFFFD=重定向,
    ;       0xFFFC=间接栈(W), 0xFFFA=间接栈(B), 0xFFFB=SRAM全局, 0xFFF8=栈变量(B)
    MOV.W @R14+, R15           ; R15 = 标记/SP调整量
    CMP.W #0xFFFF, R15         ; 结束标记？
    JEQ _restore_return_addr   ; 是→处理返回地址
    CMP.W #0xFFFE, R15         ; 间接寻址标记(MOV.W)？
    JEQ _restore_indirect      ; 是→处理间接寻址(字)
    CMP.W #0xFFF9, R15         ; 间接寻址标记(MOV.B)？
    JEQ _restore_indirect_byte ; 是→处理间接寻址(字节)
    CMP.W #0xFFFD, R15         ; 重定向间接寻址标记？
    JEQ _restore_redirect_ind  ; 是→处理重定向间接寻址
    CMP.W #0xFFFC, R15         ; 间接栈写入标记(MOV.W)？
    JEQ _restore_indirect_stack ; 是→处理间接栈写入(字)
    CMP.W #0xFFFA, R15         ; 间接栈写入标记(MOV.B)？
    JEQ _restore_indirect_stack_byte ; 是→处理间接栈写入(字节)
    CMP.W #0xFFFB, R15         ; SRAM全局变量标记？
    JEQ _restore_sram_global   ; 是→处理SRAM全局变量
    CMP.W #0xFFF8, R15         ; 栈变量(MOV.B)标记？
    JEQ _restore_stack_byte    ; 是→处理栈变量(字节)
    ; 【标准栈变量恢复】
    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电SP
    ADD.W R15, R11             ; R11 = 目标函数SP
    MOV.W @R14+, R10           ; R10 = FRAM槽位地址
    MOV.W @R10, R13            ; R13 = FRAM中的值
    MOV.W @R14+, R9            ; R9 = 栈偏移量
    MOV.W R11, R15             ; R15 = 目标函数SP
    ADD.W R9, R15              ; R15 = 目标地址
    ; 安全检查
    CMP.W #0x2400, R15
    JHS _restore_items
    CMP.W #0x1C00, R15
    JLO _restore_items
    MOV.W R13, 0(R15)          ; 写入
    JMP _restore_items

_restore_indirect:
    ; 【间接寻址恢复(字) - 支持偏移】
    ; 格式: [0xFFFE, value_slot, base_addr_slot, offset]
    MOV.W @R14+, R8            ; R8 = 值的FRAM地址
    MOV.W @R8, R9              ; R9 = 值
    MOV.W @R14+, R8            ; R8 = 基地址的FRAM地址
    MOV.W @R8, R8              ; R8 = 基地址
    MOV.W @R14+, R10           ; R10 = 偏移量
    ADD.W R10, R8              ; R8 = 基地址 + 偏移 = 目标地址
    ; 安全检查
    CMP.W #0x2400, R8
    JHS _restore_items
    CMP.W #0x1C00, R8
    JLO _restore_items
    MOV.W R9, 0(R8)            ; 写入(字)
    JMP _restore_items

_restore_indirect_byte:
    ; 【间接寻址恢复(字节)】
    ; 格式: [0xFFF9, value_slot, base_addr_slot, offset]
    MOV.W @R14+, R8            ; R8 = 值的FRAM地址
    MOV.B @R8, R9              ; R9 = 值(字节)
    MOV.W @R14+, R8            ; R8 = 基地址的FRAM地址
    MOV.W @R8, R8              ; R8 = 基地址
    MOV.W @R14+, R10           ; R10 = 偏移量
    ADD.W R10, R8              ; R8 = 基地址 + 偏移 = 目标地址
    ; 安全检查
    CMP.W #0x2400, R8
    JHS _restore_items
    CMP.W #0x1C00, R8
    JLO _restore_items
    MOV.B R9, 0(R8)            ; 写入(字节)
    JMP _restore_items

_restore_redirect_ind:
    ; 【重定向间接寻址】
    MOV.W @R14+, R8            ; R8 = 值的FRAM地址
    MOV.W @R8, R9              ; R9 = 值
    MOV.W @R14+, R8            ; R8 = 目标SP调整
    MOV.W &ASAP_SP_SAVE, R10   ; R10 = 断电SP
    ADD.W R8, R10              ; R10 += SP调整
    MOV.W @R14+, R8            ; R8 = 目标栈偏移
    ADD.W R8, R10              ; R10 += 栈偏移
    MOV.W @R14+, R8            ; R8 = 间接偏移
    ADD.W R8, R10              ; R10 = 最终目标地址
    ADD.W #2, R14              ; 跳过寄存器编号
    ; 安全检查
    CMP.W #0x2400, R10
    JHS _restore_items
    CMP.W #0x1C00, R10
    JLO _restore_items
    MOV.W R9, 0(R10)           ; 写入
    JMP _restore_items

_restore_indirect_stack:
    ; 【间接栈写入(字)】
    ; 格式：[0xFFFC, value_slot, addr_slot]
    ; 恢复：从addr_slot读取实际地址，把value写入该地址
    MOV.W @R14+, R8            ; R8 = 值的FRAM地址
    MOV.W @R8, R9              ; R9 = 值
    MOV.W @R14+, R8            ; R8 = 地址的FRAM地址
    MOV.W @R8, R10             ; R10 = 实际写入地址
    ; 安全检查：确保地址在SRAM范围内（0x1C00-0x2400）
    CMP.W #0x2400, R10
    JHS _restore_items         ; 地址超出范围，跳过
    CMP.W #0x1C00, R10
    JLO _restore_items         ; 地址超出范围，跳过
    MOV.W R9, 0(R10)           ; 写入(字)
    JMP _restore_items

_restore_indirect_stack_byte:
    ; 【间接栈写入(字节)】
    ; 格式：[0xFFFA, value_slot, addr_slot]
    ; 恢复：从addr_slot读取实际地址，把value(字节)写入该地址
    MOV.W @R14+, R8            ; R8 = 值的FRAM地址
    MOV.B @R8, R9              ; R9 = 值(字节)
    MOV.W @R14+, R8            ; R8 = 地址的FRAM地址
    MOV.W @R8, R10             ; R10 = 实际写入地址
    ; 安全检查：确保地址在SRAM范围内（0x1C00-0x2400）
    CMP.W #0x2400, R10
    JHS _restore_items         ; 地址超出范围，跳过
    CMP.W #0x1C00, R10
    JLO _restore_items         ; 地址超出范围，跳过
    MOV.B R9, 0(R10)           ; 写入(字节)
    JMP _restore_items

_restore_sram_global:
    ; 【全局变量恢复】
    ; 格式：[0xFFFB, FRAM槽位, 目标地址]
    ; 恢复：从FRAM槽位读取值，写入目标地址
    ; 注意：目标可能是SRAM(0x1C00-0x2400)或FRAM(.data段)变量
    MOV.W @R14+, R8            ; R8 = FRAM槽位地址
    MOV.W @R8, R9              ; R9 = 值
    MOV.W @R14+, R10           ; R10 = 目标地址
    ; 安全检查：确保地址有效（非0，非外设区域）
    CMP.W #0, R10
    JEQ _restore_items         ; 地址无效，跳过
    CMP.W #0x200, R10
    JLO _restore_items         ; 外设区域，跳过
    MOV.W R9, 0(R10)           ; 写入目标地址
    JMP _restore_items

_restore_stack_byte:
    ; 【栈变量恢复(字节)】
    ; 格式：[0xFFF8, SP调整, FRAM地址, 偏移]
    MOV.W @R14+, R15           ; R15 = SP调整量
    MOV.W &ASAP_SP_SAVE, R11   ; R11 = 断电SP
    ADD.W R15, R11             ; R11 = 目标函数SP
    MOV.W @R14+, R10           ; R10 = FRAM槽位地址
    MOV.B @R10, R13            ; R13 = FRAM中的值(字节)
    MOV.W @R14+, R9            ; R9 = 栈偏移量
    MOV.W R11, R15             ; R15 = 目标函数SP
    ADD.W R9, R15              ; R15 = 目标地址
    ; 安全检查
    CMP.W #0x2400, R15
    JHS _restore_items
    CMP.W #0x1C00, R15
    JLO _restore_items
    MOV.B R13, 0(R15)          ; 写入(字节)
    JMP _restore_items

_restore_return_addr:
    ; 【关键修复】循环处理调用栈上所有函数的返回地址
    ; 格式：[SP调整, FRAM地址, 偏移], ..., [0, 0, 0]表示结束
_restore_ret_loop:
    MOV.W @R14+, R15       ; R15 = SP调整
    MOV.W @R14+, R10       ; R10 = RET_ADDR地址
    CMP.W #0, R10          ; FRAM地址=0表示结束
    JEQ _restore_skip_ret_addr
    ; 恢复返回地址
    MOV.W @R14+, R9        ; R9 = 偏移
    MOV.W &ASAP_SP_SAVE, R11
    ADD.W R15, R11         ; R11 = 该函数SP
    MOV.W @R10, R13        ; R13 = 返回地址
    ADD.W R11, R9          ; R9 = 目标地址
    ; 安全检查
    CMP.W #0x2400, R9
    JHS _restore_ret_loop  ; 地址超出范围，跳过此返回地址，继续下一个
    CMP.W #0x1C00, R9
    JLO _restore_ret_loop  ; 地址超出范围，跳过此返回地址，继续下一个
    MOV.W R13, 0(R9)       ; 写入返回地址
    JMP _restore_ret_loop  ; 继续处理下一个返回地址

_restore_skip_ret_addr:
    ADD.W #2, R14          ; 跳过偏移字段（结束标记的占位符）

_restore_get_pc:
    ; 跳过 PC 占位符（已在查表时读取）
    ADD.W #2, R14          ; 跳过 PC 字段

_restore_sp:
    ; 恢复栈指针
    MOV.W &ASAP_SP_SAVE, SP

_restore_jump:
    ; ===== P1.3 置低（标记恢复完成） =====
    BIC.B #0x08, &0x0202          ; P1OUT &= ~BIT3 (P1.3置低)
    ; 注意：不修改P1.2状态，让应用程序自己管理
    ; 【关键修复】清除已恢复标志（而非设置为0x1234）
    ; 原因：恢复跳转后会跳过__main_continue处的flag清除代码
    ;       如果flag残留为0x1234，下次断电后SRAM可能保留此值
    ;       导致误判为"已恢复"而跳过必要的恢复
    MOV.W #0, &__asap_restored_flag  ; 清除flag

    ; ===== 恢复寄存器（防止垃圾值覆盖栈） =====
    ; WID设置后紧跟的写入可能使用寄存器，需要先恢复
    CMP.W #3, &ASAP_WID_SAVE
    JNE _skip_restore_R12_3
    MOV.W &__SLOT_REG_R12, R12    ; 恢复R12 (WID 3后使用)
_skip_restore_R12_3:
    CMP.W #4, &ASAP_WID_SAVE
    JNE _skip_restore_R13_4
    MOV.W &__SLOT_REG_R13, R13    ; 恢复R13 (WID 4后使用)
_skip_restore_R13_4:
    CMP.W #9, &ASAP_WID_SAVE
    JNE _skip_restore_R13_9
    MOV.W &__SLOT_REG_R13, R13    ; 恢复R13 (WID 9后使用)
_skip_restore_R13_9:
    CMP.W #10, &ASAP_WID_SAVE
    JNE _skip_restore_R14_10
    MOV.W &__SLOT_REG_R14, R14    ; 恢复R14 (WID 10后使用)
_skip_restore_R14_10:
    CMP.W #15, &ASAP_WID_SAVE
    JNE _skip_restore_R13_15
    MOV.W &__SLOT_REG_R13, R13    ; 恢复R13 (WID 15后使用)
_skip_restore_R13_15:
    ; 【关键】恢复SP到断电时的值
    MOV.W &ASAP_SP_SAVE, R1
    ; 清除WID（防止重复恢复）
    MOV.W #0, &ASAP_WID_SAVE
    ; 跳转到恢复PC
    MOV.W &ASAP_PC_SAVE, PC

_restore_end:
    ; 冷启动或恢复失败
    ; ===== P1.3 保持高（标记恢复失败/异常） =====
    ; BIC.B #0x08, &0x0202          ; P1OUT &= ~BIT3 (注释：不置低，保持高作为错误指示)
    RET

