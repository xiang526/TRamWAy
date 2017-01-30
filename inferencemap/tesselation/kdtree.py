
from .base import *
from inferencemap.spatial.scaler import *
from math import *
import numpy as np
import pandas as pd
from threading import Lock
import itertools
import scipy.sparse as sparse
from inferencemap.spatial.dichotomy import ConnectedDichotomy


def _face_hash(v1, n1):
	'''key that identify a same face.'''
	return tuple(v1) + tuple(n1)


class KDTreeMesh(Voronoi):
	"""k-dimensional tree (quad tree in 2D) based tesselation.

	Attributes:
		scaler: see :class:`Tesselation`.
		min_probability (float): minimum probability of a point to be in a given cell.
		max_probability (float): maximum probability of a point to be in a given cell.
		max_level (float): maximum level, considering that the smallest cells are at level 0
			and the level increments each time the cell size doubles.
		_min_distance (float, private): scaled minimum distance between neighbor cell centers.
		_avg_distance (float, private): scaled average distance between neighbor cell centers.
	"""
	def __init__(self, scaler=Scaler(), min_distance=None, avg_distance=None, \
		min_probability=None, max_probability=None, max_level=None, **kwargs):
		Voronoi.__init__(self, scaler)
		self._min_distance = min_distance
		self._avg_distance = avg_distance
		self.min_probability = min_probability
		if min_probability and not max_probability:
			max_probability = 10.0 * min_probability
		self.max_probability = max_probability
		self.max_level = max_level

	def cellIndex(self, points, min_cell_size=None, max_cell_size=None, prefered='index', \
		inclusive_min_cell_size=None, metric='chebyshev', **kwargs):
		if prefered == 'force index':
			min_cell_size = None
		if min_cell_size is not None:
			raise NotImplementedError('kd-tree is not adapted to partitioning with min_cell_size constraint; use min_probability at tesselation time instead')
		#if max_cell_size: # only if points are those the tesselation was grown with
		#	t_max_cell_size = int(floor(self.max_probability * points.shape[0]))
		#	if max_cell_size < t_max_cell_size:
		#		max_cell_size = None
		if metric == 'chebyshev':
			if min_cell_size or max_cell_size or inclusive_min_cell_size:
				raise NotImplementedError('knn support has evolved and KDTreeMesh still lacks a proper support of min_cell_size, max_cell_size and inclusive_min_cell_size. You can still call cellIndex with argument metric=\'euclidean\'')
			# TODO: pass relevant kwargs to cdist
			points = self.scaler.scalePoint(points, inplace=False)
			D = cdist(self.descriptors(points, asarray=True), \
				self._cell_centers, metric) # , **kwargs
			dmax = self.dichotomy.reference_length[self.level[np.newaxis,:] + 1]
			I, J = np.nonzero(D <= dmax)
			if I[0] == 0 and I.size == points.shape[0] and I[-1] == points.shape[0] - 1:
				return J
			else:
				K = -np.ones(points.shape[0], dtype=J.dtype)
				K[I] = J
				return K
		else:
			return Delaunay.cellIndex(self, points, min_cell_size=min_cell_size, \
				max_cell_size=max_cell_size, prefered=prefered, \
				inclusive_min_cell_size=inclusive_min_cell_size, metric=metric, \
				**kwargs)

	def tesselate(self, points, **kwargs):
		init = self.scaler.init
		points = self._preprocess(points)
		if init:
			if self._min_distance:
				self._min_distance = self.scaler.scaleDistance(self._min_distance)
			if self._avg_distance:
				self._avg_distance = self.scaler.scaleDistance(self._avg_distance)
		min_distance = None
		avg_distance = None
		if self._avg_distance:
			avg_distance = self._avg_distance
		elif self._min_distance:
			min_distance = self._min_distance
		min_count = int(round(self.min_probability * points.shape[0]))
		max_count = int(round(self.max_probability * points.shape[0]))
		self.dichotomy = ConnectedDichotomy(self.descriptors(points, asarray=True), \
			min_count=min_count, max_count=max_count, \
			min_edge=min_distance, base_edge=avg_distance, max_level=self.max_level)
		del self.max_level
		self.dichotomy.split()
		self.dichotomy.subset = {} # clear memory
		self.dichotomy.subset_counter = 0
		
		origin, level = zip(*[ self.dichotomy.cell[c][:2] for c in range(self.dichotomy.cell_counter) ])
		origin = np.vstack(origin)
		self.level = np.array(level)
		self._cell_centers = origin + self.dichotomy.reference_length[self.level[:, np.newaxis] + 1]
		adjacency = np.vstack([ self.dichotomy.adjacency[e] for e in range(self.dichotomy.edge_counter) \
			if e in self.dichotomy.adjacency ]).T
		self._cell_adjacency = sparse.csr_matrix((np.ones(adjacency.shape[1], dtype=int), \
			(adjacency[0], adjacency[1])), shape=(self.dichotomy.cell_counter, self.dichotomy.cell_counter))

		# quick and dirty Voronoi construction: vertices are introduced as many times as they
		# appear in a ridge, and as many ridges are introduced as four times the number of 
		# centers. In a second step, duplicate vertices are removed.
		def unique_rows(data, *args, **kwargs):
			uniq = np.unique(data.view(data.dtype.descr * data.shape[1]), *args, **kwargs)
			if isinstance(uniq, tuple):
				return (uniq[0].view(data.dtype).reshape(-1, data.shape[1]),) + tuple(uniq[1:])
			else:
				return uniq.view(data.dtype).reshape(-1, data.shape[1])
		n = origin.shape[0]
		self._cell_vertices = []
		self._ridge_vertices = []
		for i, v1 in enumerate(self.dichotomy.unit_hypercube):
			self._cell_vertices.append(origin + \
				np.float_(v1) * self.dichotomy.reference_length[self.level[:, np.newaxis]])
			for jj, v2 in enumerate(self.dichotomy.unit_hypercube[i+1:]):
				if np.sum(v1 != v2) == 1: # neighbors in the voronoi
					j = i + 1 + jj
					self._ridge_vertices.append(np.vstack(\
						np.hstack((np.arange(i * n, (i+1) * n)[:,np.newaxis], \
							np.arange(j * n, (j+1) * n)[:,np.newaxis]))))
		self._cell_vertices, I = unique_rows(np.concatenate(self._cell_vertices, axis=0), \
			return_inverse=True)
		self._ridge_vertices = I[np.concatenate(self._ridge_vertices, axis=0)]
		#self._postprocess()
