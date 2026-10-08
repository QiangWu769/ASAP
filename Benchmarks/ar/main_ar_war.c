#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

#define LOOP_IDX 1

// ========== 配置参数 (恢复原值) ==========
#define NUM_WARMUP_SAMPLES 3      // 保持 3，手动展开
#define ACCEL_WINDOW_SIZE 3       // 保持 3，手动展开
#define MODEL_SIZE 16             // 恢复为 16
#define SAMPLES_TO_COLLECT 8      // 恢复为 8
#define SAMPLE_NOISE_FLOOR 10

// ========== 类型定义 ==========
// 强制 4 字节对齐
typedef struct __attribute__((aligned(4))) {
    uint8_t x;
    uint8_t y;
    uint8_t z;
    uint8_t padding; 
} threeAxis_t_8;

typedef threeAxis_t_8 accelReading;
typedef accelReading accelWindow[ACCEL_WINDOW_SIZE];

typedef struct {
    unsigned meanmag;
    unsigned stddevmag;
} features_t;

typedef enum {
    CLASS_STATIONARY,
    CLASS_MOVING,
} class_t;

typedef struct {
    features_t stationary[MODEL_SIZE];
    features_t moving[MODEL_SIZE];
} model_t;

typedef enum {
    MODE_IDLE = 3,
    MODE_TRAIN_STATIONARY = 2,
    MODE_TRAIN_MOVING = 1,
    MODE_RECOGNIZE = 0,
    MODE_EXIT = 255
} run_mode_t;

typedef struct {
    unsigned totalCount;
    unsigned movingCount;
    unsigned stationaryCount;
} stats_t;

// ========== 全局变量 ==========
unsigned count = 0;
unsigned seed = 1;
unsigned cnt = 0;
model_t model;  // 改为全局变量以便ASAP正确备份/恢复

// ========== 辅助函数 ==========

// 16位平方根，保持固定次数循环 (0..8)，分析工具友好
static unsigned sqrt16(unsigned x) {
    if (x == 0) return 0;
    unsigned result = 0;
    for (unsigned bit = 1 << 14; bit != 0; bit >>= 2) {
        if (bit > x) continue;
        if (x >= result + bit) {
            x -= result + bit;
            result = (result >> 1) + bit;
        } else {
            result >>= 1;
        }
    }
    return result;
}

void accel_sample(accelReading* result){
    result->x = (seed * 17) % 85;
    result->y = (seed * 17 * 17) % 85;
    result->z = (seed * 17 * 17 * 17) % 85;
}

// ========== 核心逻辑 (手动展开小循环) ==========

// 展开：预热3次
void warmup_sensor()
{
    accelReading sample;
    
    // 样本 1
    accel_sample(&sample);
    seed++;
    
    // 样本 2
    accel_sample(&sample);
    seed++;

    // 样本 3
    accel_sample(&sample);
    seed++;
}

// 展开：获取3个样本
void acquire_window(accelWindow window)
{
    // 样本 1
    accel_sample(&window[0]);
    seed++;
    
    // 样本 2
    accel_sample(&window[1]);
    seed++;

    // 样本 3
    accel_sample(&window[2]);
    seed++;
}

// 展开：处理3个样本的噪声
void transform(accelWindow window)
{
    accelReading *sample;

    // 样本 1
    sample = &window[0];
    if (sample->x < SAMPLE_NOISE_FLOOR || sample->y < SAMPLE_NOISE_FLOOR || sample->z < SAMPLE_NOISE_FLOOR) {
        sample->x = (sample->x > SAMPLE_NOISE_FLOOR) ? sample->x : 0;
        sample->y = (sample->y > SAMPLE_NOISE_FLOOR) ? sample->y : 0;
        sample->z = (sample->z > SAMPLE_NOISE_FLOOR) ? sample->z : 0;
    }

    // 样本 2
    sample = &window[1];
    if (sample->x < SAMPLE_NOISE_FLOOR || sample->y < SAMPLE_NOISE_FLOOR || sample->z < SAMPLE_NOISE_FLOOR) {
        sample->x = (sample->x > SAMPLE_NOISE_FLOOR) ? sample->x : 0;
        sample->y = (sample->y > SAMPLE_NOISE_FLOOR) ? sample->y : 0;
        sample->z = (sample->z > SAMPLE_NOISE_FLOOR) ? sample->z : 0;
    }

    // 样本 3
    sample = &window[2];
    if (sample->x < SAMPLE_NOISE_FLOOR || sample->y < SAMPLE_NOISE_FLOOR || sample->z < SAMPLE_NOISE_FLOOR) {
        sample->x = (sample->x > SAMPLE_NOISE_FLOOR) ? sample->x : 0;
        sample->y = (sample->y > SAMPLE_NOISE_FLOOR) ? sample->y : 0;
        sample->z = (sample->z > SAMPLE_NOISE_FLOOR) ? sample->z : 0;
    }
}

// 展开：计算特征值 (Mean 和 StdDev)
void featurize(features_t *features, accelWindow aWin)
{
    accelReading mean;
    mean.x = mean.y = mean.z = 0;
    
    // 1. 计算均值 (展开求和)
    mean.x = aWin[0].x + aWin[1].x + aWin[2].x;
    mean.y = aWin[0].y + aWin[1].y + aWin[2].y;
    mean.z = aWin[0].z + aWin[1].z + aWin[2].z;
    
    mean.x >>= 2; // 除以 4 (虽然窗口是3，但原代码是移位2，保持原逻辑)
    mean.y >>= 2;
    mean.z >>= 2;

    accelReading stddev;
    stddev.x = stddev.y = stddev.z = 0;

    // 2. 计算标准差 (展开累加)
    // 样本 1
    stddev.x += (aWin[0].x > mean.x) ? (aWin[0].x - mean.x) : (mean.x - aWin[0].x);
    stddev.y += (aWin[0].y > mean.y) ? (aWin[0].y - mean.y) : (mean.y - aWin[0].y);
    stddev.z += (aWin[0].z > mean.z) ? (aWin[0].z - mean.z) : (mean.z - aWin[0].z);
    
    // 样本 2
    stddev.x += (aWin[1].x > mean.x) ? (aWin[1].x - mean.x) : (mean.x - aWin[1].x);
    stddev.y += (aWin[1].y > mean.y) ? (aWin[1].y - mean.y) : (mean.y - aWin[1].y);
    stddev.z += (aWin[1].z > mean.z) ? (aWin[1].z - mean.z) : (mean.z - aWin[1].z);

    // 样本 3
    stddev.x += (aWin[2].x > mean.x) ? (aWin[2].x - mean.x) : (mean.x - aWin[2].x);
    stddev.y += (aWin[2].y > mean.y) ? (aWin[2].y - mean.y) : (mean.y - aWin[2].y);
    stddev.z += (aWin[2].z > mean.z) ? (aWin[2].z - mean.z) : (mean.z - aWin[2].z);
    
    stddev.x >>= 2;
    stddev.y >>= 2;
    stddev.z >>= 2;

    unsigned meanmag = mean.x*mean.x + mean.y*mean.y + mean.z*mean.z;
    unsigned stddevmag = stddev.x*stddev.x + stddev.y*stddev.y + stddev.z*stddev.z;

    features->meanmag   = sqrt16(meanmag);
    features->stddevmag = sqrt16(stddevmag);
}

class_t classify(features_t *features, model_t *model)
{
    int move_less_error = 0;
    int stat_less_error = 0;
    features_t *model_features;
    int i;

    // 这里的循环 (0..15) 较大，不手动展开，
    // 但因为内部调用的子函数已经没有循环了，CFG 复杂度大大降低。
    for (i = 0; i < MODEL_SIZE; ++i) {
        // Stationary Check
        model_features = &model->stationary[i];
        long int stat_mean_err = (model_features->meanmag > features->meanmag) 
            ? (model_features->meanmag - features->meanmag) 
            : (features->meanmag - model_features->meanmag);
            
        long int stat_sd_err = (model_features->stddevmag > features->stddevmag) 
            ? (model_features->stddevmag - features->stddevmag) 
            : (features->stddevmag - model_features->stddevmag);

        // Moving Check
        model_features = &model->moving[i];
        long int move_mean_err = (model_features->meanmag > features->meanmag) 
            ? (model_features->meanmag - features->meanmag) 
            : (features->meanmag - model_features->meanmag);
            
        long int move_sd_err = (model_features->stddevmag > features->stddevmag) 
            ? (model_features->stddevmag - features->stddevmag) 
            : (features->stddevmag - model_features->stddevmag);

        if (move_mean_err < stat_mean_err) move_less_error++; else stat_less_error++;
        if (move_sd_err < stat_sd_err) move_less_error++; else stat_less_error++;
    }

    return (move_less_error > stat_less_error) ? CLASS_MOVING : CLASS_STATIONARY;
}

void record_stats(stats_t *stats, class_t class)
{
    stats->totalCount++;
    if (class == CLASS_MOVING) stats->movingCount++;
    else stats->stationaryCount++;
}

void print_stats(stats_t *stats)
{
    if (stats->totalCount > 0) {
        unsigned resultStationaryPct = stats->stationaryCount * 100 / stats->totalCount;
        unsigned resultMovingPct = stats->movingCount * 100 / stats->totalCount;
    }
}

void train(features_t *classModel)
{
    accelWindow sampleWindow;
    features_t features;
    unsigned i;

    // 已手动展开
    warmup_sensor();

    for (i = 0; i < MODEL_SIZE; ++i) {
        // 这里的三个函数内部现在都是线性代码，没有循环
        acquire_window(sampleWindow);
        transform(sampleWindow);
        featurize(&features, sampleWindow);
        classModel[i] = features;
    }
}

void recognize(model_t *model)
{
    stats_t stats = {0, 0, 0};
    accelWindow sampleWindow;
    features_t features;
    class_t class;
    unsigned i;

    for (i = 0; i < SAMPLES_TO_COLLECT; ++i) {
        acquire_window(sampleWindow);
        transform(sampleWindow);
        featurize(&features, sampleWindow);
        class = classify(&features, model);
        record_stats(&stats, class);
    }
    print_stats(&stats);
}

run_mode_t select_mode(uint8_t *prev_pin_state)
{
    uint8_t pin_state = 1;
    count++;
    if(count >= 2) pin_state = 2;
    if(count >= 3) pin_state = 0;
    if(count >= 4) {
        cnt++;
        if(cnt == LOOP_IDX) return MODE_EXIT;
        count = 0;
        seed = 1;
        *prev_pin_state = MODE_IDLE;
        pin_state = 99; 
    }
    
    if ((pin_state == MODE_TRAIN_STATIONARY || pin_state == MODE_TRAIN_MOVING) && pin_state == *prev_pin_state) {
        pin_state = MODE_IDLE;
    } else {
        *prev_pin_state = pin_state;
    }
    return (run_mode_t)pin_state;
}

// ========== 主函数 ==========
int main()
{
    uint8_t prev_pin_state = MODE_IDLE;
    
    cnt = 0;
    count = 0; 
    seed = 1;

    run_mode_t current_mode = MODE_IDLE;
    
    // 主循环：使用变量判断退出，避免死循环结构
    while (current_mode != MODE_EXIT) {
        current_mode = select_mode(&prev_pin_state);
        
        // 显式跳转
        if (current_mode == MODE_EXIT) continue;

        switch (current_mode) {
            case MODE_TRAIN_STATIONARY:
                train(model.stationary);
                break;
            case MODE_TRAIN_MOVING:
                train(model.moving);
                break;
            case MODE_RECOGNIZE:
                recognize(&model);
                break;
            default:
                break;
        }
    }
    return 0;
}

