#ifndef DNN_H
#define DNN_H

#include "includes/matlib/mat.h"
#include <stdbool.h>
#include <stdint.h>

#define CONFIG_LAYER_BUF_SIZE 3200
#define LAYER_BUF_NUMBER 3

extern fixed layer_buffers[LAYER_BUF_NUMBER][CONFIG_LAYER_BUF_SIZE];

typedef struct {
    bool same_padding;
    uint16_t stride[3];
    uint16_t size[3];
} dnn_param;

extern dnn_param params;

void convol_impl(mat_t *src, mat_t *dest, mat_t *w, mat_t *b, bool depth);
#define convol(s, d, w, b)       convol_impl(s, d, w, b, false)
#define convol_depth(s, d, w, b) convol_impl(s, d, w, b, true)

void fc_sparse(mat_t *src, mat_t *dest, mat_t *weight, mat_t *bias);
void fc_dense(mat_t *src, mat_t *dest, mat_t *weight, mat_t *bias);
void pooling(mat_t *src, mat_t *dest);
void relu(mat_t *src, mat_t *dest);
uint16_t prediction(mat_t *src);

#endif
