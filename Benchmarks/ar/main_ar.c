#include <msp430.h>
#include <stdint.h>
#include <stdbool.h>

// 使用本地简化版libio（只依赖msp430.h）
#include "libio/log.h"

// 简单的BITSET宏
#define BITSET(port, val) ((port) |= (val))

// TIMER配置：0=正常运行，1=定时器模拟断电
#ifndef TIMER
#define TIMER 1
#endif

// param.h中定义的循环次数（如果没有则默认为1）
#ifndef LOOP_IDX
#define LOOP_IDX 100
#endif

// ========== AR算法类型定义 ==========
typedef struct {
	uint8_t x;
	uint8_t y;
	uint8_t z;
#ifdef __clang__
	uint8_t padding; // clang crashes with type size mismatch assert failure
#endif
} threeAxis_t_8;

typedef threeAxis_t_8 accelReading;

// Number of samples to discard before recording training set
#define NUM_WARMUP_SAMPLES 3
#define ACCEL_WINDOW_SIZE 3
#define MODEL_SIZE 16
#define SAMPLE_NOISE_FLOOR 10

// Number of classifications to complete in one experiment
#define SAMPLES_TO_COLLECT 8

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

// ========== 全局变量 ==========
unsigned count = 0;
unsigned seed = 1;
unsigned cnt = 0;

// 全局model（改为全局变量以便ASAP正确备份/恢复）
model_t model;

// ========== 定时器中断（仅TIMER==1时）==========
#if TIMER == 1
__attribute__((interrupt(TIMER0_B1_VECTOR)))
void TimerB1_ISR(void){
	PMMCTL0 = PMMPW | PMMSWPOR;
	BITSET(TBCTL, TBCLR);
}
#endif

// ========== 数学库函数 ==========
// 简化的16位平方根函数
static inline unsigned sqrt16(unsigned x) {
	if (x == 0) return 0;
	
	unsigned result = 0;
	unsigned bit = 1 << 14; // 最高位
	
	while (bit > x)
		bit >>= 2;
	
	while (bit != 0) {
		if (x >= result + bit) {
			x -= result + bit;
			result = (result >> 1) + bit;
		} else {
			result >>= 1;
		}
		bit >>= 2;
	}
	return result;
}

// ========== AR核心算法函数 ==========
void accel_sample(unsigned seed, accelReading* result){
	result->x = (seed*17)%85;
	result->y = (seed*17*17)%85;
	result->z = (seed*17*17*17)%85;
}

void acquire_window(accelWindow window)
{
	accelReading sample;
	unsigned samplesInWindow = 0;

	while (samplesInWindow < ACCEL_WINDOW_SIZE) {
		accel_sample(seed, &sample);
		// LOG("seed: %u\r\n", seed);
		seed++;
		// LOG("acquire: sample %u %u %u\r\n", sample.x, sample.y, sample.z);

		window[samplesInWindow++] = sample;
	}
}

void transform(accelWindow window)
{
	unsigned i = 0;

	// LOG("transform\r\n");

	for (i = 0; i < ACCEL_WINDOW_SIZE; i++) {
		accelReading *sample = &window[i];

		if (sample->x < SAMPLE_NOISE_FLOOR ||
				sample->y < SAMPLE_NOISE_FLOOR ||
				sample->z < SAMPLE_NOISE_FLOOR) {

			// LOG("transform: sample %u %u %u\r\n",
			// 		sample->x, sample->y, sample->z);

			sample->x = (sample->x > SAMPLE_NOISE_FLOOR) ? sample->x : 0;
			sample->y = (sample->y > SAMPLE_NOISE_FLOOR) ? sample->y : 0;
			sample->z = (sample->z > SAMPLE_NOISE_FLOOR) ? sample->z : 0;
		}
	}
}

void featurize(features_t *features, accelWindow aWin)
{
	// LOG("feat %x\r\n", features);
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
	
	stddev.x >>= 2;
	stddev.y >>= 2;
	stddev.z >>= 2;

	unsigned meanmag = mean.x*mean.x + mean.y*mean.y + mean.z*mean.z;
	unsigned stddevmag = stddev.x*stddev.x + stddev.y*stddev.y + stddev.z*stddev.z;

	features->meanmag   = sqrt16(meanmag);
	features->stddevmag = sqrt16(stddevmag);

	// LOG("featurize: mean %u sd %u\r\n", features->meanmag, features->stddevmag);
}

class_t classify(features_t *features, model_t *model)
{
	// LOG("cf %x\r\n", features);
	int move_less_error = 0;
	int stat_less_error = 0;
	features_t *model_features;
	int i;
	// LOG("check3: mn %u sd %u %u\r\n",
	// 		model->moving[15].meanmag, model->moving[15].stddevmag);

	// LOG("mean %u stddev %u\r\n", features->meanmag, features->stddevmag);
	for (i = 0; i < MODEL_SIZE; ++i) {
		model_features = &model->stationary[i];
		// LOG("stat mean %u stddev %u\r\n", model_features->meanmag, model_features->stddevmag);

		long int stat_mean_err = (model_features->meanmag > features->meanmag)
			? (model_features->meanmag - features->meanmag)
			: (features->meanmag - model_features->meanmag);

		long int stat_sd_err = (model_features->stddevmag > features->stddevmag)
			? (model_features->stddevmag - features->stddevmag)
			: (features->stddevmag - model_features->stddevmag);

		model_features = &model->moving[i];
		// LOG("moving mean %u stddev %u %u\r\n", model_features->meanmag, model_features->stddevmag, i);

		long int move_mean_err = (model_features->meanmag > features->meanmag)
			? (model_features->meanmag - features->meanmag)
			: (features->meanmag - model_features->meanmag);

		long int move_sd_err = (model_features->stddevmag > features->stddevmag)
			? (model_features->stddevmag - features->stddevmag)
			: (features->stddevmag - model_features->stddevmag);

		// LOG("mme %x %x sme %x %x\r\n", (unsigned)(move_mean_err >> 16), (unsigned)(move_mean_err), (unsigned)(stat_mean_err >> 16), (unsigned)(stat_mean_err));
		if (move_mean_err < stat_mean_err) {
			move_less_error++;
		} else {
			stat_less_error++;
		}

		// LOG("mse %x %x sse %x %x\r\n", (unsigned)(move_sd_err >> 16), (unsigned)(move_sd_err), (unsigned)(stat_sd_err >> 16), (unsigned)(stat_sd_err));
		if (move_sd_err < stat_sd_err) {
			move_less_error++;
		} else {
			stat_less_error++;
		}
	}
	// LOG("me %u se %u\r\n", move_less_error, stat_less_error);

	class_t class = move_less_error > stat_less_error ?
		CLASS_MOVING : CLASS_STATIONARY;
	// LOG("classify: class %u\r\n", class);

	return class;
}

void record_stats(stats_t *stats, class_t class)
{
	stats->totalCount++;

	switch (class) {
		case CLASS_MOVING:
			stats->movingCount++;
			break;

		case CLASS_STATIONARY:
			stats->stationaryCount++;
			break;
	}

	// LOG("stats: s %u m %u t %u\r\n",
	// 		stats->stationaryCount, stats->movingCount, stats->totalCount);
}

void print_stats(stats_t *stats)
{
	(void)stats;
}

void warmup_sensor()
{
	unsigned discardedSamplesCount = 0;
	accelReading sample;

	// LOG("warmup\r\n");

	while (discardedSamplesCount++ < NUM_WARMUP_SAMPLES) {
		accel_sample(seed, &sample);
		// LOG("seed: %u\r\n", seed);
		seed++;
	}
}

void train(features_t *classModel)
{
	accelWindow sampleWindow;
	features_t features;
	unsigned i;

	warmup_sensor();

	for (i = 0; i < MODEL_SIZE; ++i) {
		PRINTF("tr[");
		PRINTF_UINT(i);
		PRINTF("]");
		acquire_window(sampleWindow);
		transform(sampleWindow);
		featurize(&features, sampleWindow);

		classModel[i] = features;
	}

	// LOG("train: done: mn %u sd %u\r\n",
	// 		features.meanmag, features.stddevmag);
}

void recognize(model_t *model)
{
	stats_t stats;
	accelWindow sampleWindow;
	features_t features;
	class_t class;
	unsigned i;

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
	}

	print_stats(&stats);
}

run_mode_t select_mode(uint8_t *prev_pin_state)
{
	uint8_t pin_state = 1;

	count++;
	// LOG("count: %u\r\n", count);
	if(count >= 2) pin_state = 2;
	if(count >= 3) pin_state = 0;
	if(count >= 4) {
		PRINTF("end\r\n");
		cnt++;
		// ===== 完整执行完一轮：P1.2置低并输出complete =====
		P1OUT &= ~BIT2;  // P1.2置低
		
		PRINTF("complete\r\n");
		// 继续下一轮前P1.2置高
		//while(1);
		__delay_cycles(40000);  // 延迟5ms
		P1OUT |= BIT2;   // P1.2置高
		// 不停止，持续循环
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

	// LOG("selectMode: pins %04x\r\n", pin_state);

	return (run_mode_t)pin_state;
}

// ========== 初始化函数 ==========
void init()
{
	// 1. 关闭看门狗
	WDTCTL = WDTPW | WDTHOLD;
	
		// 6. 解锁GPIO（必须在GPIO操作前）
		PM5CTL0 &= ~LOCKLPM5;
	
		// 7. P1.2初始化并置高（标记程序开始）
		P1DIR |= BIT2;
		P1OUT |= BIT2;

	// 2. 配置时钟为8MHz（必须在UART配置前）
	CSCTL0_H = 0xA5;
	CSCTL1 = DCOFSEL_6;  // DCO = 8MHz
	CSCTL2 = SELA_0 | SELS_3 | SELM_3;  // ACLK=XT1, SMCLK=DCO, MCLK=DCO
	CSCTL3 = DIVA_0 | DIVS_0 | DIVM_0;  // 不分频
	
	// 3. 配置UART: 8MHz / 16 / 4.34 ≈ 115200 bps
	UCA0CTLW0 = UCSWRST;  // 开始配置（设置复位）
	UCA0CTLW0 |= UCSSEL__SMCLK;
	UCA0BR0 = 4;           // 8MHz / 16 / 115200 = 4.34
	UCA0BR1 = 0;
	UCA0MCTLW = UCOS16 | UCBRF_5 | (0x55 << 8);  // 过采样x16, UCBRF=5, UCBRS=0x55
	
	// 4. 配置UART引脚（P2.0=TXD, P2.1=RXD）
	P2SEL1 |= BIT0 | BIT1;
	P2SEL0 &= ~(BIT0 | BIT1);
	
	// 5. 解除UART复位（启用UART）
	UCA0CTLW0 &= ~UCSWRST;
	

	
	// 8. 定时器配置（如果启用）——与Chinchilla原版一致
#if TIMER == 1
	// ACLK=32768Hz(LFXT), /8=4096Hz, CCR1=40 → 40/4096≈9.77ms≈10ms
	BITSET(TBCTL, (TBSSEL_1 | ID_3 | MC_2 | TBCLR));
	BITSET(TBCCTL1, CCIE);
#ifndef TIMER_VALUE
#define TIMER_VALUE 40
#endif
	TBCCR1 = TIMER_VALUE;
#endif
	
	// 9. 使能中断
	__enable_interrupt();
}

// ========== 主函数 ==========
int main()
{
	init();
	

	
	uint8_t prev_pin_state = MODE_IDLE;
	// model_t model;  // 已改为全局变量
	cnt = 0;
	
	while (1) {
		if (count == 0) {
			PRINTF("start\r\n");
		}
		
		run_mode_t mode = select_mode(&prev_pin_state);
		switch (mode) {
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

