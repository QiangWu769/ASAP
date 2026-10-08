#ifndef DNN_CALC_H
#define DNN_CALC_H

#include "includes/matlib/mat.h"

void con_mul(mat_t *src, mat_t *dest, mat_t *filter);
void fc_sparse_mul(mat_t *src, mat_t *dest, mat_t *filter);
void fc_dense_mul(mat_t *src, mat_t *dest, mat_t *filter);
void ds_zero(mat_t *src, mat_t *dest);
void ds_add(mat_t *src, mat_t *dest, mat_t *filter);
void dm_add(mat_t *src, mat_t *dest, mat_t *bias);

#endif
