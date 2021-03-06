# Copyright 1999-2020 Alibaba Group Holding Ltd.
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

import warnings
from abc import ABCMeta, abstractmethod

import cloudpickle
import numpy as np
from sklearn.base import BaseEstimator, MultiOutputMixin

from ... import tensor as mt
from ...tensor.reshape.reshape import _reshape as reshape_unchecked
from ..metrics.pairwise import PAIRWISE_DISTANCE_FUNCTIONS
from ..metrics import pairwise_distances
from ..utils import check_array
from ..utils.validation import check_is_fitted
from ._ball_tree import BallTree, ball_tree_query, SklearnBallTree
from ._kd_tree import KDTree, kd_tree_query, SklearnKDTree
from ._faiss import build_faiss_index, faiss_query, METRIC_TO_FAISS_METRIC_TYPE


VALID_METRICS = dict(ball_tree=SklearnBallTree.valid_metrics,
                     kd_tree=SklearnKDTree.valid_metrics,
                     # The following list comes from the
                     # sklearn.metrics.pairwise doc string
                     brute=(list(PAIRWISE_DISTANCE_FUNCTIONS.keys()) +
                            ['braycurtis', 'canberra', 'chebyshev',
                             'correlation', 'cosine', 'dice', 'hamming',
                             'jaccard', 'kulsinski', 'mahalanobis',
                             'matching', 'minkowski', 'rogerstanimoto',
                             'russellrao', 'seuclidean', 'sokalmichener',
                             'sokalsneath', 'sqeuclidean',
                             'yule', 'wminkowski']),
                     faiss=list(METRIC_TO_FAISS_METRIC_TYPE),)


VALID_METRICS_SPARSE = dict(ball_tree=[],
                            kd_tree=[],
                            brute=(PAIRWISE_DISTANCE_FUNCTIONS.keys() -
                                   {'haversine'}))


class NeighborsBase(BaseEstimator, MultiOutputMixin, metaclass=ABCMeta):
    """Base class for nearest neighbors estimators."""

    @abstractmethod
    def __init__(self, n_neighbors=None, radius=None,
                 algorithm='auto', leaf_size=30, metric='minkowski',
                 p=2, metric_params=None, n_jobs=None):

        self.n_neighbors = n_neighbors
        self.radius = radius
        self.algorithm = algorithm
        self.leaf_size = leaf_size
        self.metric = metric
        self.metric_params = metric_params
        self.p = p
        self.n_jobs = n_jobs
        self._check_algorithm_metric()

    def _check_algorithm_metric(self):
        if self.algorithm not in ['auto', 'brute', 'kd_tree', 'ball_tree', 'faiss']:
            raise ValueError("unrecognized algorithm: '%s'" % self.algorithm)

        if self.algorithm == 'auto':
            if self.metric == 'precomputed':
                alg_check = 'brute'
            elif (callable(self.metric) or
                  self.metric in VALID_METRICS['ball_tree']):
                alg_check = 'ball_tree'
            else:
                alg_check = 'brute'
        else:
            alg_check = self.algorithm

        if callable(self.metric):
            if self.algorithm == 'kd_tree':
                # callable metric is only valid for brute force and ball_tree
                raise ValueError(
                    "kd_tree algorithm does not support callable metric '%s'"
                    % self.metric)
        elif self.metric not in VALID_METRICS[alg_check]:
            raise ValueError("Metric '%s' not valid. Use "
                             "sorted(sklearn.neighbors.VALID_METRICS['%s']) "
                             "to get valid options. "
                             "Metric can also be a callable function."
                             % (self.metric, alg_check))

        if self.metric_params is not None and 'p' in self.metric_params:
            warnings.warn("Parameter p is found in metric_params. "
                          "The corresponding parameter from __init__ "
                          "is ignored.", SyntaxWarning, stacklevel=3)
            effective_p = self.metric_params['p']
        else:
            effective_p = self.p

        if self.metric in ['wminkowski', 'minkowski'] and effective_p < 1:
            raise ValueError("p must be greater than one for minkowski metric")

    def _fit(self, X, session=None, run_kwargs=None):
        self._check_algorithm_metric()
        if self.metric_params is None:
            self.effective_metric_params_ = {}
        else:
            self.effective_metric_params_ = self.metric_params.copy()

        effective_p = self.effective_metric_params_.get('p', self.p)
        if self.metric in ['wminkowski', 'minkowski']:
            self.effective_metric_params_['p'] = effective_p

        self.effective_metric_ = self.metric
        # For minkowski distance, use more efficient methods where available
        if self.metric == 'minkowski':
            p = self.effective_metric_params_.pop('p', 2)
            if p < 1:  # pragma: no cover
                raise ValueError("p must be greater than one "
                                 "for minkowski metric")
            elif p == 1:
                self.effective_metric_ = 'manhattan'
            elif p == 2:
                self.effective_metric_ = 'euclidean'
            elif p == np.inf:
                self.effective_metric_ = 'chebyshev'
            else:
                self.effective_metric_params_['p'] = p

        if isinstance(X, NeighborsBase):
            self._fit_X = X._fit_X
            self._tree = X._tree
            self._fit_method = X._fit_method
            return self

        elif isinstance(X, SklearnBallTree):
            self._fit_X = mt.tensor(X.data)
            self._tree = X
            self._fit_method = 'ball_tree'
            return self

        elif isinstance(X, SklearnKDTree):
            self._fit_X = mt.tensor(X.data)
            self._tree = X
            self._fit_method = 'kd_tree'
            return self

        X = check_array(X, accept_sparse=True)

        if X.issparse():
            if self.algorithm not in ('auto', 'brute'):
                warnings.warn("cannot use tree with sparse input: "
                              "using brute force")
            if self.effective_metric_ not in VALID_METRICS_SPARSE['brute'] \
                    and not callable(self.effective_metric_):
                raise ValueError("Metric '%s' not valid for sparse input. "
                                 "Use sorted(sklearn.neighbors."
                                 "VALID_METRICS_SPARSE['brute']) "
                                 "to get valid options. "
                                 "Metric can also be a callable function."
                                 % (self.effective_metric_))
            self._fit_X = X.copy()
            self._tree = None
            self._fit_method = 'brute'
            return self

        self._fit_method = self.algorithm
        self._fit_X = X

        if self._fit_method == 'auto':
            # A tree approach is better for small number of neighbors,
            # and KDTree is generally faster when available
            if ((self.n_neighbors is None or
                 self.n_neighbors < self._fit_X.shape[0] // 2) and
                    self.metric != 'precomputed'):
                if self.effective_metric_ in VALID_METRICS['kd_tree']:
                    self._fit_method = 'kd_tree'
                elif (callable(self.effective_metric_) or
                      self.effective_metric_ in VALID_METRICS['ball_tree']):
                    self._fit_method = 'ball_tree'
                else:
                    self._fit_method = 'brute'
            else:
                self._fit_method = 'brute'

        if self._fit_method == 'ball_tree':
            tree = BallTree(X, self.leaf_size,
                            metric=self.effective_metric_,
                            **self.effective_metric_params_)
            self._tree = cloudpickle.loads(
                tree.execute(session=session, **(run_kwargs or dict())))
        elif self._fit_method == 'kd_tree':
            tree = KDTree(X, self.leaf_size,
                          metric=self.effective_metric_,
                          **self.effective_metric_params_)
            self._tree = cloudpickle.loads(
                tree.execute(session=session, **(run_kwargs or dict())))
        elif self._fit_method == 'brute':
            self._tree = None
        elif self._fit_method == 'faiss':
            faiss_index = build_faiss_index(X, metric=self.effective_metric_,
                                            **self.effective_metric_params_)
            faiss_index.execute(session=session, fetch=False, **(run_kwargs or dict()))
            self._faiss_index = faiss_index
        else:  # pragma: no cover
            raise ValueError("algorithm = '%s' not recognized"
                             % self.algorithm)

        if self.n_neighbors is not None:
            if self.n_neighbors <= 0:
                raise ValueError(
                    "Expected n_neighbors > 0. Got %d" %
                    self.n_neighbors
                )
            else:
                if not np.issubdtype(type(self.n_neighbors), np.integer):
                    raise TypeError(
                        "n_neighbors does not take %s value, "
                        "enter integer value" %
                        type(self.n_neighbors))

        return self


class KNeighborsMixin:
    """Mixin for k-neighbors searches"""

    def kneighbors(self, X=None, n_neighbors=None, return_distance=True,
                   session=None, run_kwargs=None, **kw):
        check_is_fitted(self, ["_fit_method", "_fit_X"], all_or_any=any)

        if n_neighbors is None:
            n_neighbors = self.n_neighbors
        elif n_neighbors <= 0:
            raise ValueError(
                "Expected n_neighbors > 0. Got %d" %
                n_neighbors
            )
        else:
            if not np.issubdtype(type(n_neighbors), np.integer):
                raise TypeError(
                    "n_neighbors does not take %s value, "
                    "enter integer value" %
                    type(n_neighbors))

        if X is not None:
            query_is_train = False
            X = check_array(X, accept_sparse=True)
        else:
            query_is_train = True
            X = self._fit_X
            # Include an extra neighbor to account for the sample itself being
            # returned, which is removed later
            n_neighbors += 1

        train_size = self._fit_X.shape[0]
        if n_neighbors > train_size:
            raise ValueError(
                "Expected n_neighbors <= n_samples, "
                " but n_samples = %d, n_neighbors = %d" %
                (train_size, n_neighbors)
            )
        n_samples, _ = X.shape
        sample_range = mt.arange(n_samples)[:, None]

        if self._fit_method == 'brute':
            # for efficiency, use squared euclidean distances
            kwds = ({'squared': True} if self.effective_metric_ == 'euclidean'
                    else self.effective_metric_params_)

            dist = pairwise_distances(X, self._fit_X, metric=self.effective_metric_,
                                      **kwds)
            neigh_dist, neigh_ind = mt.topk(dist, n_neighbors, largest=False, sorted=True,
                                            return_index=True)
            if return_distance:
                if self.effective_metric_ == 'euclidean':
                    result = mt.sqrt(neigh_dist), neigh_ind
                else:
                    result = neigh_dist, neigh_ind
            else:
                result = neigh_ind
        elif self._fit_method in ['ball_tree', 'kd_tree']:
            if X.issparse():
                raise ValueError(
                    "%s does not work with sparse matrices. Densify the data, "
                    "or set algorithm='brute'" % self._fit_method)

            query = ball_tree_query if self._fit_method == 'ball_tree' else kd_tree_query
            result = query(self._tree, X, n_neighbors, return_distance)
        elif self._fit_method == 'faiss':
            if X.issparse():
                raise ValueError(
                    "%s does not work with sparse matrices. Densify the data, "
                    "or set algorithm='brute'" % self._fit_method)
            result = faiss_query(self._faiss_index, X, n_neighbors, return_distance, **kw)
        else:  # pragma: no cover
            raise ValueError("internal: _fit_method not recognized")

        if not query_is_train:
            if isinstance(result, (tuple, list)):
                result = mt.ExecutableTuple(result)
            result.execute(session=session, fetch=False,
                           **(run_kwargs or dict()))
            return result
        else:
            # If the query data is the same as the indexed data, we would like
            # to ignore the first nearest neighbor of every sample, i.e
            # the sample itself.
            if return_distance:
                dist, neigh_ind = result
            else:
                neigh_ind = result

            sample_mask = neigh_ind != sample_range

            # Corner case: When the number of duplicates are more
            # than the number of neighbors, the first NN will not
            # be the sample, but a duplicate.
            # In that case mask the first duplicate.
            dup_gr_nbrs = mt.all(sample_mask, axis=1)
            sample_mask[:, 0] = mt.where(dup_gr_nbrs, False, sample_mask[:, 0])

            neigh_ind = reshape_unchecked(
                neigh_ind[sample_mask], (n_samples, n_neighbors - 1))

            if return_distance:
                dist = reshape_unchecked(
                    dist[sample_mask], (n_samples, n_neighbors - 1))
                ret = mt.ExecutableTuple([dist, neigh_ind])
                ret.execute(session=session, fetch=False,
                            **(run_kwargs or dict()))
                return ret
            neigh_ind.execute(session=session, fetch=False,
                              **(run_kwargs or dict()))
            return neigh_ind


class UnsupervisedMixin:
    def fit(self, X, y=None, session=None, run_kwargs=None):
        """Fit the model using X as training data

        Parameters
        ----------
        X : {array-like, tensor, BallTree, KDTree}
            Training data. If tensor, shape [n_samples, n_features],
            or [n_samples, n_samples] if metric='precomputed'.
        """
        return self._fit(X, session=session, run_kwargs=run_kwargs)
