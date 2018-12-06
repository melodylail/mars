#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 1999-2018 Alibaba Group Holding Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np

from .... import opcodes as OperandDef
from ....serialize import Int32Field
from ....config import options
from ..utils import decide_chunks
from .diag import TensorDiagBase
from .core import TensorNoInput


class TensorEye(TensorNoInput, TensorDiagBase):
    _op_type_ = OperandDef.TENSOR_EYE

    _k = Int32Field('k')

    def __init__(self, k=None, dtype=None, gpu=None, sparse=False, **kw):
        dtype = np.dtype(dtype or 'f8')
        super(TensorEye, self).__init__(_k=k, _dtype=dtype, _gpu=gpu, _sparse=sparse, **kw)

    @property
    def k(self):
        return getattr(self, '_k', 0)

    @classmethod
    def _get_nsplits(cls, op):
        tensor = op.outputs[0]
        chunk_size = tensor.params.raw_chunks or options.tensor.chunks
        return decide_chunks(tensor.shape, chunk_size, tensor.dtype.itemsize)

    @classmethod
    def _get_chunk(cls, op, chunk_k, chunk_shape, chunk_idx):
        chunk_op = TensorEye(k=chunk_k, dtype=op.dtype, gpu=op.gpu, sparse=op.sparse)
        return chunk_op.new_chunk(None, chunk_shape, index=chunk_idx)

    @classmethod
    def tile(cls, op):
        return TensorDiagBase.tile(op)


def eye(N, M=None, k=0, dtype=None, sparse=False, gpu=False, chunks=None):
    """
    Return a 2-D tensor with ones on the diagonal and zeros elsewhere.

    Parameters
    ----------
    N : int
      Number of rows in the output.
    M : int, optional
      Number of columns in the output. If None, defaults to `N`.
    k : int, optional
      Index of the diagonal: 0 (the default) refers to the main diagonal,
      a positive value refers to an upper diagonal, and a negative value
      to a lower diagonal.
    dtype : data-type, optional
      Data-type of the returned tensor.
    sparse: bool, optional
        Create sparse tensor if True, False as default
    gpu : bool, optional
        Allocate the tensor on GPU if True, False as default
    chunks : int or tuple of int or tuple of ints, optional
        Desired chunk size on each dimension

    Returns
    -------
    I : Tensor of shape (N,M)
      An tensor where all elements are equal to zero, except for the `k`-th
      diagonal, whose values are equal to one.

    See Also
    --------
    identity : (almost) equivalent function
    diag : diagonal 2-D tensor from a 1-D tensor specified by the user.

    Examples
    --------
    >>> import mars.tensor as mt

    >>> mt.eye(2, dtype=int).execute()
    array([[1, 0],
           [0, 1]])
    >>> mt.eye(3, k=1).execute()
    array([[ 0.,  1.,  0.],
           [ 0.,  0.,  1.],
           [ 0.,  0.,  0.]])

    """
    if M is None:
        M = N

    shape = (N, M)
    op = TensorEye(k, dtype=dtype, gpu=gpu, sparse=sparse)
    return op(shape, chunks=chunks)
