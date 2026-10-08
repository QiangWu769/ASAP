/*
 * WARio Benchmark: Cuckoo Filter
 * Fixed: Replaced rand() to solve linker error, kept original logic
 */

#include <stdint.h>
#include <stdbool.h>

// 1. 哑巴宏 (防止报错)
#define PRINTF(...)
#define LOG(...)

// 2. 参数配置
#define LOOP_IDX 1


#define NUM_BUCKETS 128 
#define MAX_RELOCATIONS 8
#define NUM_KEYS (NUM_BUCKETS / 4) 
#define INIT_KEY 0x1

typedef uint16_t value_t;
typedef uint16_t hash_t;
typedef uint16_t fingerprint_t;
typedef uint16_t index_t;

// ========== 全局变量 ==========
// filter 显式声明为全局变量，确保 ASAP 能正确追踪
fingerprint_t filter[NUM_BUCKETS];

// 自定义 PRNG 种子，替代 rand()
unsigned cf_rand_seed = 1;

// ========== 自定义伪随机数生成器 ==========
// 简单的线性同余生成器 (LCG)，替代 stdlib 的 rand()
static unsigned cf_rand(void)
{
    cf_rand_seed = cf_rand_seed * 1103515245 + 12345;
    return (cf_rand_seed >> 16) & 0x7FFF;
}

// 4. 核心算法
static hash_t djb_hash(uint8_t* data, unsigned len) {
    uint32_t hash = 5381;
    unsigned int i;
    for(i = 0; i < len; data++, i++) {
        hash = ((hash << 5) + hash) + (*data);
    }
    return hash & 0xFFFF;
}

static index_t hash_fp_to_index(fingerprint_t fp) {
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(fingerprint_t));
    return hash & (NUM_BUCKETS - 1);
}

static index_t hash_key_to_index(value_t fp) {
    hash_t hash = djb_hash((uint8_t *)&fp, sizeof(value_t));
    return hash & (NUM_BUCKETS - 1);
}

static fingerprint_t hash_to_fingerprint(value_t key) {
    return djb_hash((uint8_t *)&key, sizeof(value_t));
}

static value_t generate_key(value_t prev_key) {
    return (prev_key + 1) * 17;
}

// 插入操作 - filter 现在是全局变量，不再作为参数传递
static bool insert(value_t key) {
    fingerprint_t fp1, fp2, fp_victim, fp_next_victim;
    index_t index_victim, fp_hash_victim;
    unsigned relocation_count = 0;

    fingerprint_t fp = hash_to_fingerprint(key);
    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;

    fp1 = filter[index1];
    if (!fp1) { 
        filter[index1] = fp;
    } else {
        fp2 = filter[index2];
        if (!fp2) { 
            filter[index2] = fp;
        } else { 
            // 使用自定义 cf_rand() 替代 rand()
            if (cf_rand() & 0x80) { 
                index_victim = index1;
                fp_victim = fp1;
            } else {
                index_victim = index2;
                fp_victim = fp2;
            }

            filter[index_victim] = fp; 

            do { 
                fp_hash_victim = hash_fp_to_index(fp_victim);
                index_victim = index_victim ^ fp_hash_victim;
                fp_next_victim = filter[index_victim];
                filter[index_victim] = fp_victim;
                fp_victim = fp_next_victim;
            } while (fp_victim && ++relocation_count < MAX_RELOCATIONS);

            if (fp_victim) {
                return false;
            }
        }
    }
    return true;
}

// 查找操作 - filter 现在是全局变量，不再作为参数传递
static bool lookup(value_t key) {
    fingerprint_t fp = hash_to_fingerprint(key);
    index_t index1 = hash_key_to_index(key);
    index_t fp_hash = hash_fp_to_index(fp);
    index_t index2 = index1 ^ fp_hash;
    return filter[index1] == fp || filter[index2] == fp;
}

// 5. 主函数
int main(void)
{
    unsigned i;
    value_t key;
    
    // 必须加 volatile，否则 -O3 会把整个计算过程删掉（因为不算结果也没人看）
    volatile unsigned inserts = 0;
    volatile unsigned members = 0;

    // 保留你的循环结构
    for (unsigned cnt = 0; cnt < LOOP_IDX; ++cnt) {
        
        // 初始化 filter（全局变量）
        for (i = 0; i < NUM_BUCKETS; ++i)
            filter[i] = 0;
        
        // 重置随机数种子（确保每轮相同的随机序列，保持确定性）
        cf_rand_seed = 1;

        // 插入
        key = INIT_KEY;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            if (insert(key)) inserts++;
        }

        // 查找
        key = INIT_KEY;
        for (i = 0; i < NUM_KEYS; ++i) {
            key = generate_key(key);
            if (lookup(key)) members++;
        }
    }

    return 0;
}
