#include <msp430.h>

#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct {
	uint8_t x;
	uint8_t y;
	uint8_t z;
#ifdef __clang__
	uint8_t padding; // clang crashes with type size mismatch assert failure
#endif
} threeAxis_t_8;

#include <libio/builtins.h>

// 简化版：直接定义宏，不需要外部库
#ifdef LOGIC
#define PRINTF(...)
#define BLOCK_PRINTF(...)
#define BLOCK_PRINTF_BEGIN(...)
#define BLOCK_PRINTF_END(...)
#define INIT_CONSOLE(...)
#else
#include <libio/log.h>
#endif
#include <libio/mem.h>
#include <libio/msp-math.h>

#include "param.h"
#include "pins.h"
// TIMER is defined by Makefile: -DTIMER=0 or -DTIMER=1

__nv unsigned count = 0;
__nv unsigned seed = 1;
__nv unsigned cnt;

// ===== 断电模拟变量（使用 FRAM 非易失性存储）=====
#if TIMER == 1
// ⭐ 定时器基于 VLOCLK (10kHz) / 8 = 1250 Hz
// 周期 = count / 1250 (秒)
// 示例: count=125 → 0.1秒, count=250 → 0.2秒
#define min_pf 200  // 最小断电间隔: 200/1250 = 0.16秒 = 160ms
__attribute__((section(".upper.noinit"))) int timer_count = 250;  // 初始值: 0.2秒
__attribute__((section(".upper.noinit"))) volatile unsigned int random_num;
__attribute__((section(".upper.noinit"))) int mod5_rand;
#endif

/* This is for progress reporting only */

// Number of samples to discard before recording training set
#define NUM_WARMUP_SAMPLES 3

#define ACCEL_WINDOW_SIZE 3
//#define ACCEL_WINDOW_SIZE 30
#define MODEL_SIZE 16
#define SAMPLE_NOISE_FLOOR 10 // TODO: made up value

// Number of classifications to complete in one experiment
#define SAMPLES_TO_COLLECT 8

#ifdef ACCEL_16BIT_TYPE
typedef threeAxis_t accelReading;
#else // !ACCEL_16BIT_TYPE
typedef threeAxis_t_8 accelReading;
#endif // !ACCEL_16BIT_TYPE

static void init_hw()
{
	// Disable watchdog timer
	WDTCTL = WDTPW | WDTHOLD;
	
	// Unlock GPIO (for MSP430FR5969)
	PM5CTL0 &= ~LOCKLPM5;
	
	// Setup clock to 8MHz DCO
	CSCTL0_H = CSKEY_H;                    // Unlock CS registers
	CSCTL1 = DCORSEL | DCOFSEL_3;          // Set DCO to 8MHz
	CSCTL2 = SELA__VLOCLK | SELS_3 | SELM_3;  // ⭐ ACLK = VLOCLK (10kHz), SMCLK = MCLK = DCO
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;     // Set all dividers to 1
}

#if TIMER == 1
// Timer B0 interrupt handler with random power failure simulation
__attribute__((interrupt(TIMER0_B0_VECTOR)))
void TimerB0_ISR(void){
	// 使用随机数生成下次断电时间（避免固定模式）
	random_num = RTCPS;  // 读取 RTC 预分频器作为随机源
	mod5_rand = random_num % 31;  // 0~30
	random_num = min_pf + mod5_rand * 10;  // 范围: 200~500 (0.16s~0.4s)
	timer_count = random_num;
	
	// 触发软件复位（模拟断电）
	PMMCTL0 = PMMPW | PMMSWPOR;
	BITSET(TBCTL, TBCLR);
}
#endif

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
	MODE_RECOGNIZE = 0, // default
} run_mode_t;

typedef struct {
	unsigned totalCount;
	unsigned movingCount;
	unsigned stationaryCount;
} stats_t;

void accel_sample(unsigned seed, accelReading* result){
	result->x = (seed*17)%85;
	result->y = (seed*17*17)%85;
	result->z = (seed*17*17*17)%85;
}

void acquire_window(accelWindow window)
{
	accelReading sample;
	unsigned samplesInWindow = 0;

	while ( samplesInWindow < ACCEL_WINDOW_SIZE) {
		accel_sample(seed, &sample);
		// PRINTF("s=");
		// PRINTF_UINT(seed);
		// PRINTF(" ");
		seed++;
		// PRINTF("acq:");
		// PRINTF_UINT(sample.x);
		// PRINTF(",");
		// PRINTF_UINT(sample.y);
		// PRINTF(",");
		// PRINTF_UINT(sample.z);
		// PRINTF(" ");
		window[samplesInWindow++] = sample;
	}
}


void transform(accelWindow window)
{
	unsigned i = 0;

	// PRINTF("xfm ");
	for (i = 0; i < ACCEL_WINDOW_SIZE; i++) {
		accelReading *sample = &window[i];

		if (sample->x < SAMPLE_NOISE_FLOOR ||
				sample->y < SAMPLE_NOISE_FLOOR ||
				sample->z < SAMPLE_NOISE_FLOOR) {

			// PRINTF("xfm:");
			// PRINTF_UINT(sample->x);
			// PRINTF(",");
			// PRINTF_UINT(sample->y);
			// PRINTF(",");
			// PRINTF_UINT(sample->z);
			// PRINTF(" ");

			sample->x = (sample->x > SAMPLE_NOISE_FLOOR) ? sample->x : 0;
			sample->y = (sample->y > SAMPLE_NOISE_FLOOR) ? sample->y : 0;
			sample->z = (sample->z > SAMPLE_NOISE_FLOOR) ? sample->z : 0;
		}
	}
}


void featurize(features_t *features, accelWindow aWin)
{
	accelReading mean;
	accelReading stddev;

	mean.x = mean.y = mean.z = 0;
	stddev.x = stddev.y = stddev.z = 0;
	int i;
	for (i = 0; i < ACCEL_WINDOW_SIZE; i++) {
		mean.x += aWin[i].x;  // x
		mean.y += aWin[i].y;  // y
		mean.z += aWin[i].z;  // z
	}
	/*
		 mean.x = mean.x / ACCEL_WINDOW_SIZE;
		 mean.y = mean.y / ACCEL_WINDOW_SIZE;
		 mean.z = mean.z / ACCEL_WINDOW_SIZE;
	 */
	mean.x >>= 2;
	mean.y >>= 2;
	mean.z >>= 2;

	for (i = 0; i < ACCEL_WINDOW_SIZE; i++) {
		stddev.x += aWin[i].x > mean.x ? aWin[i].x - mean.x
			: mean.x - aWin[i].x;  // x
		stddev.y += aWin[i].y > mean.y ? aWin[i].y - mean.y
			: mean.y - aWin[i].y;  // y
		stddev.z += aWin[i].z > mean.z ? aWin[i].z - mean.z
			: mean.z - aWin[i].z;  // z
	}
	/*
		 stddev.x = stddev.x / (ACCEL_WINDOW_SIZE - 1);
		 stddev.y = stddev.y / (ACCEL_WINDOW_SIZE - 1);
		 stddev.z = stddev.z / (ACCEL_WINDOW_SIZE - 1);
	 */
	stddev.x >>= 2;
	stddev.y >>= 2;
	stddev.z >>= 2;

	unsigned meanmag = mean.x*mean.x + mean.y*mean.y + mean.z*mean.z;
	unsigned stddevmag = stddev.x*stddev.x + stddev.y*stddev.y + stddev.z*stddev.z;

	features->meanmag   = sqrt16(meanmag);
	features->stddevmag = sqrt16(stddevmag);
	// PRINTF("feat:mn=");
	// PRINTF_UINT(features->meanmag);
	// PRINTF(" sd=");
	// PRINTF_UINT(features->stddevmag);
	// PRINTF(" ");
}

class_t classify(features_t *features, model_t *model)
{
	int move_less_error = 0;
	int stat_less_error = 0;
	features_t *model_features;
	int i;
	
	// PRINTF("clf:mn=");
	// PRINTF_UINT(features->meanmag);
	// PRINTF(",sd=");
	// PRINTF_UINT(features->stddevmag);
	// PRINTF(" ");

	for (i = 0; i < MODEL_SIZE; ++i) {
		model_features = &model->stationary[i];

		long int stat_mean_err = (model_features->meanmag > features->meanmag)
			? (model_features->meanmag - features->meanmag)
			: (features->meanmag - model_features->meanmag);

		long int stat_sd_err = (model_features->stddevmag > features->stddevmag)
			? (model_features->stddevmag - features->stddevmag)
			: (features->stddevmag - model_features->stddevmag);

		model_features = &model->moving[i];

		long int move_mean_err = (model_features->meanmag > features->meanmag)
			? (model_features->meanmag - features->meanmag)
			: (features->meanmag - model_features->meanmag);

		long int move_sd_err = (model_features->stddevmag > features->stddevmag)
			? (model_features->stddevmag - features->stddevmag)
			: (features->stddevmag - model_features->stddevmag);

		if (move_mean_err < stat_mean_err) {
			move_less_error++;
		} else {
			stat_less_error++;
		}

		if (move_sd_err < stat_sd_err) {
			move_less_error++;
		} else {
			stat_less_error++;
		}
	}
	
	// PRINTF("me=");
	// PRINTF_UINT(move_less_error);
	// PRINTF(",se=");
	// PRINTF_UINT(stat_less_error);
	// PRINTF(" ");

	class_t class = move_less_error > stat_less_error ?
		CLASS_MOVING : CLASS_STATIONARY;
	// PRINTF("cls=");
	// PRINTF_UINT(class);
	// PRINTF(" ");

	return class;
}

void record_stats(stats_t *stats, class_t class)
{
	/* stats->totalCount, stats->movingCount, and stats->stationaryCount have an
	 * nv-internal consistency requirement.  This code should be atomic. */

	stats->totalCount++;

	switch (class) {
		case CLASS_MOVING:
			stats->movingCount++;
			break;

		case CLASS_STATIONARY:
			stats->stationaryCount++;
			break;
	}
	
	// PRINTF("sts:s=");
	// PRINTF_UINT(stats->stationaryCount);
	// PRINTF(",m=");
	// PRINTF_UINT(stats->movingCount);
	// PRINTF(",t=");
	// PRINTF_UINT(stats->totalCount);
	// PRINTF(" ");
}

void print_stats(stats_t *stats)
{
	unsigned resultStationaryPct = stats->stationaryCount * 100 / stats->totalCount;
	unsigned resultMovingPct = stats->movingCount * 100 / stats->totalCount;

	unsigned sum = stats->stationaryCount + stats->movingCount;

	PRINTF("stats: s ");
	PRINTF_UINT(stats->stationaryCount);
	PRINTF(" (");
	PRINTF_UINT(resultStationaryPct);
	PRINTF("%) m ");
	PRINTF_UINT(stats->movingCount);
	PRINTF(" (");
	PRINTF_UINT(resultMovingPct);
	PRINTF("%) sum/tot ");
	PRINTF_UINT(sum);
	PRINTF("/");
	PRINTF_UINT(stats->totalCount);
	PRINTF(": ");
	if (sum == stats->totalCount && sum == SAMPLES_TO_COLLECT) {
		PRINTF("V\r\n");
	} else {
		PRINTF("X\r\n");
	}
}

void warmup_sensor()
{
	unsigned discardedSamplesCount = 0;
	accelReading sample;

	PRINTF("warmup\r\n");
	while ( discardedSamplesCount++ < NUM_WARMUP_SAMPLES) {
		accel_sample(seed, &sample);
		seed++;
	}
}

void train(features_t *classModel)
{
	accelWindow sampleWindow;
	features_t features;
	unsigned i;

	PRINTF("train:start\r\n");
	warmup_sensor();

	for (i = 0; i < MODEL_SIZE; ++i) {
		PRINTF("tr[");
		PRINTF_UINT(i);
		PRINTF("]");
		
		acquire_window(sampleWindow);
		transform(sampleWindow);
		featurize(&features, sampleWindow);

		classModel[i] = features;
		
		PRINTF("ok\r\n");  // 简洁输出：每次循环结束
	}

	PRINTF("train:done mn=");
	PRINTF_UINT(features.meanmag);
	PRINTF(",sd=");
	PRINTF_UINT(features.stddevmag);
	PRINTF("\r\n");
}

void recognize(model_t *model)
{
	stats_t stats;
	accelWindow sampleWindow;
	features_t features;
	class_t class;
	unsigned i;

	PRINTF("recog:start\r\n");
	stats.totalCount = 0;
	stats.stationaryCount = 0;
	stats.movingCount = 0;

	for (i = 0; i < SAMPLES_TO_COLLECT; ++i) {
		PRINTF("rc[");
		PRINTF_UINT(i);
		PRINTF("]");
		
		acquire_window(sampleWindow);
		transform(sampleWindow);
		featurize(&features, sampleWindow);
		class = classify(&features, model);
		record_stats(&stats, class);
		
		PRINTF("ok\r\n");  // 简洁输出：每次循环结束
	}

	print_stats(&stats);
	PRINTF("recog:done\r\n");
}

run_mode_t select_mode(uint8_t *prev_pin_state)
{
	uint8_t pin_state = 1;

	count++;
	PRINTF("cnt=");
	PRINTF_UINT(count);
	PRINTF(" ");
	if(count >= 2) pin_state = 2;
	if(count >= 3) pin_state = 0;
	if(count >= 4) {
		PRINTF("end\r\n");
		cnt++;
		if (cnt == LOOP_IDX) {
//#ifdef LOGIC
			// Out high
//			GPIO(PORT_AUX, OUT) |= BIT(PIN_AUX_2);
			// Out low
//			GPIO(PORT_AUX, OUT) &= ~BIT(PIN_AUX_2);
//#endif
			// Program complete, halt
			while(1);
		}
		count = 0;
		seed = 1;
		*prev_pin_state = MODE_IDLE;
		pin_state = 99;
	}
	// Don't re-launch training after finishing training
	if ((pin_state == MODE_TRAIN_STATIONARY ||
				pin_state == MODE_TRAIN_MOVING) &&
			pin_state == *prev_pin_state) {
		pin_state = MODE_IDLE;
	} else {
		*prev_pin_state = pin_state;
	}

	PRINTF("mode=");
	PRINTF_UINT(pin_state);
	PRINTF(" ");
	return (run_mode_t)pin_state;
}

void init()
{
	init_hw();
	INIT_CONSOLE();
	__enable_interrupt();
}

int main()
{
	init();
	
	// 【热启动检测】检测stage5b设置的标志
	volatile uint16_t hot_flag = *(volatile uint16_t *)0x6850;
	if (hot_flag == 0xABCD) {
		// 进入了热启动路径，但_asap_restore返回了→恢复失败
		PRINTF("===HOT_START=== WID=");
		PRINTF_UINT(*(volatile uint16_t *)0x7000);
		PRINTF(" FAIL!\r\n");
		*(volatile uint16_t *)0x1C00 = 0;  // 清除flag允许重试
	}
	
	uint8_t prev_pin_state = MODE_IDLE;
	model_t model;

	cnt = 0;
	
	while (1) {
		if (count == 0) {
			if (cnt == 0) {
// #ifdef LOGIC
// 				// Out high
// 				GPIO(PORT_AUX, OUT) |= BIT(PIN_AUX_1);
// 				// Out low
// 				GPIO(PORT_AUX, OUT) &= ~BIT(PIN_AUX_1);
// #endif
			}
			PRINTF("start\r\n");
		}

		run_mode_t mode = select_mode(&prev_pin_state);
		switch (mode) {
			case MODE_TRAIN_STATIONARY:
				PRINTF("MODE:stat\r\n");
				train(model.stationary);
				break;
			case MODE_TRAIN_MOVING:
				PRINTF("MODE:move\r\n");
				train(model.moving);
				PRINTF("chk0:mn=");
				PRINTF_UINT(model.moving[15].meanmag);
				PRINTF(",sd=");
				PRINTF_UINT(model.moving[15].stddevmag);
				PRINTF("\r\n");
				break;
			case MODE_RECOGNIZE:
				PRINTF("MODE:recog\r\n");
				PRINTF("chk1:mn=");
				PRINTF_UINT(model.moving[15].meanmag);
				PRINTF(",sd=");
				PRINTF_UINT(model.moving[15].stddevmag);
				PRINTF("\r\n");
				recognize(&model);
				break;
			default:
				PRINTF("MODE:idle\r\n");
				break;
		}
	}

	return 0;
}
