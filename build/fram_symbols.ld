/* ASAP FRAM符号定义 - 支持数组 */

/* 标量槽位 */
PROVIDE(__SLOT__uart_putc_SP_1 = 0x6400);
PROVIDE(__SLOT__uart_puts_SP_0 = 0x6402);
PROVIDE(__SLOT_dnn_main_R12_0 = 0x6406);
PROVIDE(__SLOT_dnn_main_R13_0 = 0x640A);
PROVIDE(__SLOT_dnn_main_SP_0 = 0x640E);
PROVIDE(__SLOT_dnn_main_SP_10 = 0x6412);
PROVIDE(__SLOT_dnn_main_SP_12 = 0x6414);
PROVIDE(__SLOT_dnn_main_SP_14 = 0x6416);
PROVIDE(__SLOT_dnn_main_SP_16 = 0x6418);
PROVIDE(__SLOT_dnn_main_SP_18 = 0x641A);
PROVIDE(__SLOT_dnn_main_SP_2 = 0x641C);
PROVIDE(__SLOT_dnn_main_SP_20 = 0x641E);
PROVIDE(__SLOT_dnn_main_SP_22 = 0x6420);
PROVIDE(__SLOT_dnn_main_SP_24 = 0x6422);
PROVIDE(__SLOT_dnn_main_SP_26 = 0x6424);
PROVIDE(__SLOT_dnn_main_SP_28 = 0x6426);
PROVIDE(__SLOT_dnn_main_SP_30 = 0x6428);
PROVIDE(__SLOT_dnn_main_SP_32 = 0x642A);
PROVIDE(__SLOT_dnn_main_SP_34 = 0x642C);
PROVIDE(__SLOT_dnn_main_SP_36 = 0x642E);
PROVIDE(__SLOT_dnn_main_SP_38 = 0x6430);
PROVIDE(__SLOT_dnn_main_SP_4 = 0x6432);
PROVIDE(__SLOT_dnn_main_SP_40 = 0x6434);
PROVIDE(__SLOT_dnn_main_SP_42 = 0x6436);
PROVIDE(__SLOT_dnn_main_SP_44 = 0x6438);
PROVIDE(__SLOT_dnn_main_SP_46 = 0x643A);
PROVIDE(__SLOT_dnn_main_SP_48 = 0x643C);
PROVIDE(__SLOT_dnn_main_SP_50 = 0x643E);
PROVIDE(__SLOT_dnn_main_SP_52 = 0x6440);
PROVIDE(__SLOT_dnn_main_SP_6 = 0x6442);
PROVIDE(__SLOT_dnn_main_SP_8 = 0x6444);
PROVIDE(__SLOT_f_mul_SP_0 = 0x6446);
PROVIDE(__SLOT_f_mul_SP_2 = 0x644A);
PROVIDE(__SLOT_f_mul_SP_4 = 0x644C);
PROVIDE(__SLOT_main_SP_0 = 0x644E);
PROVIDE(__SLOT_my_memcpy_R12_0 = 0x6452);
PROVIDE(__SLOT_my_memcpy_SP_0 = 0x6456);
PROVIDE(__SLOT_my_memcpy_SP_2 = 0x645A);
PROVIDE(__SLOT_my_memcpy_SP_4 = 0x645C);
PROVIDE(__SLOT_my_memcpy_SP_6 = 0x645E);
PROVIDE(__SLOT_my_memcpy_SP_8 = 0x6460);

/* 间接寻址地址槽位 */
PROVIDE(__ADDR__uart_puts_SP_0 = 0x6404);
PROVIDE(__ADDR_dnn_main_R12_0 = 0x6408);
PROVIDE(__ADDR_dnn_main_R13_0 = 0x640C);
PROVIDE(__ADDR_dnn_main_SP_0 = 0x6410);
PROVIDE(__ADDR_f_mul_SP_0 = 0x6448);
PROVIDE(__ADDR_main_SP_0 = 0x6450);
PROVIDE(__ADDR_my_memcpy_R12_0 = 0x6454);
PROVIDE(__ADDR_my_memcpy_SP_0 = 0x6458);

/* SRAM全局变量槽位 (0x1C00-0x2400) */
PROVIDE(__SLOT_SRAM_count = 0x6462);  /* count */

/* 数组备份区 */
PROVIDE(__backup_buf1_start = 0x6464);
PROVIDE(__backup_buf2_start = 0x684C);
PROVIDE(__backup_fc1_b_start = 0x6C34);
PROVIDE(__backup_fc2_b_start = 0x701C);

/* ASAP系统变量 */
PROVIDE(ASAP_WID_SAVE = 0x7000);
PROVIDE(ASAP_PC_SAVE = 0x7002);
PROVIDE(ASAP_SP_SAVE = 0x7004);

/* ===== 循环数组FRAM镜像 ===== */

/* ===== 寄存器备份槽位 (stage5f) ===== */
__SLOT_REG_R12 = 0x6502;
__SLOT_REG_R13 = 0x6504;
__SLOT_REG_R14 = 0x6506;
