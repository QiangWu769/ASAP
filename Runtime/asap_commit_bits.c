/*
 * ASAP Commit Bits 存储区域
 * 必须初始化为0，放在FRAM中
 */

// 分配512字节commit bits区域（足够容纳256个WID，每个2字节对齐）
// 使用专用段.asap_commits_noinit（在FRAM，但不被CRT0初始化）
__attribute__((section(".asap_commits_noinit")))
volatile unsigned char asap_commit_bits[512];  // 不初始化！避免被CRT0清零

// 确保符号可见
void* _asap_commit_area = (void*)asap_commit_bits;

