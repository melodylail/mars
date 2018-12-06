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

from .... import operands
from ..utils import infer_dtype
from .core import TensorBinOp, TensorConstant


class TensorXor(operands.Xor, TensorBinOp):
    def __init__(self, casting='same_kind', err=None, dtype=None, sparse=False, **kw):
        err = err if err is not None else np.geterr()
        super(TensorXor, self).__init__(_casting=casting, _err=err,
                                        _dtype=dtype, _sparse=sparse, **kw)

    @classmethod
    def _is_sparse(cls, x1, x2):
        return x1.issparse() and x2.issparse()

    @classmethod
    def constant_cls(cls):
        return TensorXorConstant


class TensorXorConstant(operands.XorConstant, TensorConstant):
    def __init__(self, casting='same_kind', err=None, dtype=None, sparse=False, **kw):
        err = err if err is not None else np.geterr()
        super(TensorXorConstant, self).__init__(_casting=casting, _err=err,
                                                _dtype=dtype, _sparse=sparse, **kw)

    @classmethod
    def _is_sparse(cls, x1, x2):
        if hasattr(x1, 'issparse') and x1.issparse() and np.isscalar(x2) and x2 == 0:
            return True
        if hasattr(x2, 'issparse') and x2.issparse() and np.isscalar(x1) and x1 == 0:
            return True
        return False


@infer_dtype(np.logical_xor)
def logical_xor(x1, x2, out=None, where=None, **kwargs):
    """
    Compute the truth value of x1 XOR x2, element-wise.

    Parameters
    ----------
    x1, x2 : array_like
        Logical XOR is applied to the elements of `x1` and `x2`.  They must
        be broadcastable to the same shape.
    out : Tensor, None, or tuple of Tensor and None, optional
        A location into which the result is stored. If provided, it must have
        a shape that the inputs broadcast to. If not provided or `None`,
        a freshly-allocated tensor is returned. A tuple (possible only as a
        keyword argument) must have length equal to the number of outputs.
    where : array_like, optional
        Values of True indicate to calculate the ufunc at that position, values
        of False indicate to leave the value in the output alone.
    **kwargs

    Returns
    -------
    y : bool or Tensor of bool
        Boolean result of the logical XOR operation applied to the elements
        of `x1` and `x2`; the shape is determined by whether or not
        broadcasting of one or both arrays was required.

    See Also
    --------
    logical_and, logical_or, logical_not, bitwise_xor

    Examples
    --------
    >>> import mars.tensor as mt

    >>> mt.logical_xor(True, False).execute()
    True
    >>> mt.logical_xor([True, True, False, False], [True, False, True, False]).execute()
    array([False,  True,  True, False])

    >>> x = mt.arange(5)
    >>> mt.logical_xor(x < 1, x > 3).execute()
    array([ True, False, False, False,  True])

    Simple example showing support of broadcasting

    >>> mt.logical_xor(0, mt.eye(2)).execute()
    array([[ True, False],
           [False,  True]])
    """
    op = TensorXor(**kwargs)
    return op(x1, x2, out=out, where=where)


@infer_dtype(np.logical_xor, reverse=True)
def rlogical_xor(x1, x2, **kwargs):
    op = TensorXor(**kwargs)
    return op.rcall(x1, x2)
