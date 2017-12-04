# -*- coding: utf-8 -*-

# Copyright © 2017, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


from math import *
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
import scipy.sparse as sparse
from scipy.sparse import issparse
import scipy.spatial as spatial
from tramway.spatial.scaler import *
from tramway.core import *
#from collections import OrderedDict
from warnings import warn
import itertools
import copy


class CellStats(Lazy):
	"""Container datatype for a point dataset together with a tesselation.

	A `CellStats` instance conveniently stores the tesselation (:attr:`tesselation`) and the 
	partition of the data (:attr:`cell_index`) together with the data itself (:attr:`points`) and 
	a few more intermediate results frequently derivated from a data partition.

	The partition :attr:`cell_index` may be in any of the following formats:

	array
		Cell index of size the number of data points. The element at index ``i`` is the cell
		index of point ``i`` or ``-1`` (if point ``i`` is not assigned to any cell).

	pair of arrays
		Point-cell association in the shape of a sparse representation 
		``(point_index, cell_index)`` such that for all ``i`` ``point_index[i]`` point is in 
		``cell_index[i]`` cell.

	sparse matrix (:mod:`scipy.sparse`)
		``number_of_points * number_of_cells`` matrix with nonzero element wherever
		the corresponding point is in the corresponding cell.


	See also :meth:`Tesselation.cell_index`.


	Attributes:

		points (array-like): the original point coordinates, unchanged.

		cell_index (numpy.ndarray or pair of arrays or sparse matrix):
			Point-cell association (or data partition).

		tesselation (Tesselation):
			The tesselation that defined the partition.

		location_count (numpy.ndarray, lazy): 
			point count per cell; ``location_count[i]`` is the number of 
			points in cell ``i``.

		bounding_box (array-like, lazy):
			``2 * D`` array with lower values in first row and upper values in second row,
			where ``D`` is the dimension of the point data.

		param (dict):
			Arguments involved in the tesselation and the partition steps, as key-value 
			pairs. Such information is maintained in `CellStats` so that it can be stored
			in *.rwa.h5* files and retrieve for traceability.

	"""

	__slots__ = ['_points', '_cell_index', '_location_count', '_bounding_box', 'param', '_tesselation']
	__lazy__ = ['location_count', 'bounding_box']

	def __init__(self, cell_index=None, location_count=None, bounding_box=None, points=None, \
		tesselation=None, param={}):
		Lazy.__init__(self)
		self._points = points
		self.cell_index = cell_index
		self._location_count = location_count
		self._bounding_box = bounding_box
		self.param = param
		self._tesselation = tesselation

	@property
	def cell_index(self):
		if self._cell_index is None:
			self._cell_index = self.tesselation.cell_index(self.points)
		return self._cell_index

	@cell_index.setter
	def cell_index(self, index):
		self.__lazysetter__(index)
		self.location_count = None

	@property
	def points(self):
		return self._points

	@points.setter
	def points(self, pts):
		self._points = pts
		self.cell_index = None
		self.bounding_box = None

	@property
	def tesselation(self):
		return self._tesselation

	@tesselation.setter
	def tesselation(self, mesh):
		self._tesselation = mesh
		self.cell_index = None

	def descriptors(self, *vargs, **kwargs):
		"""Proxy method for :meth:`Tesselation.descriptors`."""
		return self.tesselation.descriptors(*vargs, **kwargs)

	@property
	def location_count(self):
		if self._location_count is None:
			ncells = self.tesselation._cell_centers.shape[0]
			if isinstance(self.cell_index, tuple):
				ci = sparse.csr_matrix((np.ones_like(self.cell_index[0], dtype=bool), \
					self.cell_index), \
					shape=(self.points.shape[0], ncells))
				self._location_count = np.diff(ci.indptr)
			elif sparse.issparse(self.cell_index):
				self._location_count = np.diff(self.cell_index.tocsc().indptr)
			else:
				valid_cell_centers, _location_count = np.unique(self.cell_index, \
					return_counts=True)
				self._location_count = np.zeros(ncells, dtype=_location_count.dtype)
				self._location_count[valid_cell_centers] = _location_count
				#center_to_point = valid_cell_centers[center_to_point]
		return self._location_count

	@location_count.setter
	def location_count(self, cc):
		self.__lazysetter__(cc)

	@property
	def bounding_box(self):
		if self._bounding_box is None:
			xmin = self.points.min(axis=0)
			xmax = self.points.max(axis=0)
			if isinstance(self.points, pd.DataFrame):
				self._bounding_box = pd.concat([xmin, xmax], axis=1).T
				self._bounding_box.index = ['min', 'max']
			else:
				self._bounding_box = np.vstack([xmin, xmax]).flatten('F')
		return self._bounding_box

	@bounding_box.setter
	def bounding_box(self, bb):
		self.__lazysetter__(bb)



def format_cell_index(K, format=None, select=None, shape=None, copy=False, **kwargs):
	"""
	Convert from any valid index format to any other.

	Arguments:

		K (any): original point-cell association representation.

		format (str): either 'array', 'pair', 'matrix', 'coo', 'csr' or 'csc'.
			See also :meth:`Tesselation.cell_index`.

		select (callable): called only if ``format == 'array'`` and points are
			associated to multiple cells; `select` takes the point index
			as first argument, the corresponding cell indices (:class:`numpy.ndarray`) 
			as second argument and the extra keyword arguments given to
			:func:`format_cell_index`.

		shape ((int, int)): number of points, number of cells.

		copy (bool): if ``True``, ensures that a copy of `K` is returned if `K`
			is already in the requested format.

	Returns:

		any: point-cell association in the requested format.

	See also :meth:`Tesselation.cell_index` and :func:`nearest_cell`.
	"""
	if isinstance(K, np.ndarray) and format not in [None, 'array']:
		K = (np.arange(K.size), K)
		copy = False # already done
	if format in ['matrix', 'coo', 'csr', 'csc']:
		if issparse(K):
			if format == 'coo':
				K = K.tocoo()
				copy = False # already done
		else:
			K = sparse.coo_matrix((np.ones_like(K[0], dtype=bool), K), shape=shape)
			copy = False # already done
		if format == 'csr':
			K = K.tocsr()
			copy = False # already done
		elif format == 'csc':
			K = K.tocsc()
			copy = False # already done
	elif issparse(K):
		K = K.tocoo()
		K = (K.row, K.col) # drop the values; keep only the indices
		copy = False # already done
	if format == 'array' and isinstance(K, tuple):
		points, cells = K
		K = np.full(shape[0], -1, dtype=int)
		P = np.unique(points)
		for p in P:
			cs = cells[points == p]
			if 1 < cs.size:
				K[p] = select(p, cs, **kwargs)
			else:
				K[p] = cs
		copy = False # already done
	if copy:
		K = copy.copy(K)
	return K


def nearest_cell(locations, cell_centers):
	"""
	Generate a function suitable for use as 
	:func:`format_cell_index`'s argument `select`.

	The returned function takes a point index and cell indices as arguments
	and returns the index of the nearest cell.

	Arguments:

		locations (array-like): location coordinates.

		cell_centers (array-like): cell center coordinates.

	Returns:

		callable: `select` function.
	"""
	def f(point, cells):
		x = locations[point,:]
		y = cell_centers[cells,:]
		z = y - x
		square_dist = sum(z * z, axis=1)
		winner = np.argmin(square_dist)
		return cells[winner]
	return f



def point_adjacency_matrix(cells, symetric=True, cell_labels=None, adjacency_labels=None):
	"""
	Adjacency matrix of data points such that a given pair of points is defined as
	adjacent iif they belong to adjacent and distinct cells.

	Arguments:
		cells (CellStats):
			CellStats with both partition and tesselation defined.

		symetric (bool, optional):
			If ``False``, the returned matrix will not be symetric, i.e. wherever i->j is
			defined, j->i is not.

		cell_labels (callable, optional):
			Takes an array of cell labels as input 
			(see :attr:`Tesselation.cell_label`)
			and returns a bool array of equal shape.

		adjacency_labels (callable, optional):
			Takes an array of edge labels as input 
			(see :attr:`Tesselation.adjacency_label`) 
			and returns a bool array of equal shape.

	Returns:
		scipy.sparse.csr_matrix: Sparse square matrix with as many rows as data points.
	"""
	if not isinstance(cells.cell_index, np.ndarray):
		raise NotImplementedError('cell overlap support has not been implemented here')
	x = cells.descriptors(cells.points, asarray=True)
	ij = np.arange(x.shape[0])
	x2 = np.sum(x * x, axis=1)
	x2.shape = (x2.size, 1)
	I = []
	J = []
	D = []
	n = []
	for i in np.arange(cells.tesselation.cell_adjacency.shape[0]):
		if cell_labels is not None and not cell_labels(cells.tesselation.cell_label[i]):
			continue
		_, js, k = sparse.find(cells.tesselation.cell_adjacency[i])
		if js.size == 0:
			continue
		# the upper triangular part of the adjacency matrix should be defined...
		k = k[i < js]
		js = js[i < js]
		if js.size == 0:
			continue
		if adjacency_labels is not None:
			if cells.tesselation.adjacency_label is not None:
				k = cells.tesselation.adjacency_label
			js = js[adjacency_labels(k)]
			if js.size == 0:
				continue
		if cell_labels is not None:
			js = js[cell_labels(cells.tesselation.cell_label[js])]
			if js.size == 0:
				continue
		ii = ij[cells.cell_index == i]
		xi = x[cells.cell_index == i]
		x2i = x2[cells.cell_index == i]
		for j in js:
			xj = x[cells.cell_index == j]
			x2j = x2[cells.cell_index == j]
			d2 = x2i + x2j.T - 2 * np.dot(xi, xj.T)
			jj = ij[cells.cell_index == j]
			i2, j2 = np.meshgrid(ii, jj, indexing='ij')
			I.append(i2.flatten())
			J.append(j2.flatten())
			D.append(d2.flatten())
			if symetric:
				I.append(j2.flatten())
				J.append(i2.flatten())
				D.append(d2.flatten())
	I = np.concatenate(I)
	J = np.concatenate(J)
	D = np.sqrt(np.concatenate(D))
	n = cells.points.shape[0]
	return sparse.csr_matrix((D, (I, J)), shape=(n, n))



class Tesselation(object):
	"""Abstract class for tesselations.

	The methods to be implemented are :meth:`tesselate` and :meth:`cell_index`.

	Attributes:
		scaler (Scaler): scaler.

		_cell_adjacency (private):
			square adjacency matrix for cells.
			If :attr:`_adjacency_label` is defined, :attr:`_cell_adjacency` should be 
			sparse and the explicit elements should be indices in :attr:`_adjacency_label`.

		_cell_label (numpy.ndarray, private):
			cell labels with as many elements as cells.

		_adjacency_label (numpy.ndarray, private):
			inter-cell edge labels with as many elements as there are edges.

	Arguments:
		scaler (Scaler): scaler.
	"""
	def __init__(self, scaler=Scaler()):
		self.scaler = scaler
		self._cell_adjacency = None
		self._cell_label = None
		self._adjacency_label = None

	def _preprocess(self, points):
		"""
		Identify euclidian variables (usually called 'x', 'y', 'z') and scale the coordinates.

		See also:
			:mod:`tramway.spatial.scaler`.
		"""
		if self._cell_centers is None and self.scaler.euclidean is None:
			# initialize
			if isstructured(points):
				self.scaler.euclidean = ['x', 'y']
				if not ('x' in points and 'y' in points): # enforce presence of 'x' and 'y'
					raise AttributeError('missing ''x'' or ''y'' in input dataframe.')
				if 'z' in points:
					self.scaler.euclidean.append('z')
			else:	self.scaler.euclidean = np.arange(0, points.shape[1])
		return self.scaler.scale_point(points)

	def tesselate(self, points, **kwargs):
		"""
		Grow the tesselation.

		Arguments:
			points (array-like): point coordinates.

		Admits keyword arguments.
		"""
		raise NotImplementedError

	def cell_index(self, points, format=None, select=None, **kwargs):
		"""
		Partition.

		The returned value depends on the ``format`` input argument:

		* ``'array'``: returns a vector ``v`` such that ``v[i]`` is cell index for 
			point index ``i`` or ``-1``.

		* ``'pair'``: returns a pair of ``I``-sized arrays ``(p, c)`` where, for each 
			point-cell association ``i`` in ``range(I)``, ``p[i]`` is a point index 
			and ``c[i]`` is a corresponding cell index.

		* ``'matrix'`` or ``'coo'`` or ``'csr'`` or ``'csc'``: 
			returns a :mod:`~scipy.sparse` matrix with points as rows and
			cells as columns; non-zeros are all ``True`` or float weights.

		By default with `format` undefined, any implementation may favor any format.

		Note that ``'array'`` may not be an acceptable format and :meth:`cell_index` may 
		not comply with ``format='index'`` unless `select` is defined.
		When a location or a translocation is associated to several cells, `select` 
		chooses a single cell among them.

		The default implementation calls :func:`format_cell_index` on the result of an
		abstract `_cell_index` method that any :class:`Tesselation` implementation can
		implement instead of :meth:`cell_index`.

		See also :func:`format_cell_index`.

		Arguments:
			points (array-like): point (location) coordinates.

			format (str): either 'vector', 'pairs' or 'matrix'
				prefered representation of the point-cell association (or partition).

			select (callable): takes the point index, an array of cell indices and the 
				tesselation as arguments, and returns a cell index or ``-1`` for no cell.

		"""
		return format_cell_index(self._cell_index(points, **kwargs), format=format, select=select,
			shape=(points.shape[0], self.cell_adjacency.shape[0]))

	# cell_label property
	@property
	def cell_label(self):
		"""Cell labels, :class:`numpy.ndarray` with as many elements as there are cells."""
		return self._cell_label

	@cell_label.setter
	def cell_label(self, label):
		self._cell_label = label

	# cell_adjacency property
	@property
	def cell_adjacency(self):
		"""Square cell adjacency matrix. If :attr:`adjacency_label` is defined, 
		:attr:`cell_adjacency` is sparse and the explicit elements are indices in 
		:attr:`adjacency_label`."""
		return self._cell_adjacency

	@cell_adjacency.setter
	def cell_adjacency(self, matrix):
		self._cell_adjacency = matrix

	# adjacency_label property
	@property
	def adjacency_label(self):
		"""Inter-cell edge labels, :class:`numpy.ndarray` with as many elements as edges."""
		return self._adjacency_label

	@adjacency_label.setter
	def adjacency_label(self, label):
		self._adjacency_label = label

	@property
	def simplified_adjacency(self):
		"""
		Simplified copy of :attr:`cell_adjacency` as a :class:`~scipy.sparse.coo_matrix` sparse 
		matrix with no explicit zeros.

		Non-zero values indicate adjacency and all these values are strictly positive.
		"""
		adj = self.cell_adjacency.tocoo()
		if self.adjacency_label is None:
			ok = 0 < adj.data
		else:
			ok = 0 < self.adjacency_label[adj.data]
		return sparse.coo_matrix((adj.data[ok], (adj.row[ok], adj.col[ok])), shape=adj.shape)

	def descriptors(self, points, asarray=False):
		"""Keep the data columns that were involved in growing the tesselation.

		Arguments:
			points (array-like): point coordinates.
			asarray (bool, optional): returns a :class:`numpy.ndarray`.

		Returns:
			array-like: coordinates. If equal to `points`, may be truly identical.

		See also:
			:meth:`tramway.spatial.scaler.Scaler.scaled`.
		"""
		try:
			return self.scaler.scaled(points, asarray)
		except:
			if asarray:
				return np.asarray(points)
			else:
				return points



class Delaunay(Tesselation):
	"""
	Delaunay graph.

	A cell is represented by a centroid and an edge of the graph represents a neighbor relationship 
	between two cells.

	:class:`Delaunay` implements the nearest neighbor feature and support for cell overlap.

	Attributes:
		_cell_centers (numpy.ndarray, private): scaled coordinates of the cell centers.
	"""
	def __init__(self, scaler=Scaler()):
		Tesselation.__init__(self, scaler)
		self._cell_centers = None

	def tesselate(self, points):
		self._cell_centers = self._preprocess(points)

	def cell_index(self, points, format=None, select=None, knn=None,
		min_location_count=None, metric='euclidean', **kwargs):
		"""
		See :meth:`Tesselation.cell_index`.

		A single array representation of the point-cell association may not be possible with
		`knn` defined, because a point can be associated to multiple cells. If such
		a case happens the default output format will be ``'pair'``.

		In addition to the values allowed by :meth:`Tesselation.cell_index`, `format` admits
		value ``'force array'`` that acts like ``format='array', select=nearest_cell(...)``.
		The implementation however is more straight-forward and simply ignores 
		the minimum number of nearest neighbours if provided.

		Arguments:
			points: see :meth:`Tesselation.cell_index`.
			format: see :meth:`Tesselation.cell_index`; additionally admits ``'force array'``.
			select: see :meth:`Tesselation.cell_index`.
			knn (int or pair of ints, optional):
				minimum number of points per cell (or of nearest neighbors to the cell 
				center). Cells may overlap and the returned cell index may be a sparse 
				point-cell association.
				can also be a pair of ints, in which case these ints define the minimum
				and maximum number of points per cell respectively.
				See also the `prefered` argument.
			min_location_count (int, optional):
				minimum number of points for a cell to be included in the labeling. 
				This argument applies before `knn`. The points in these cells, if not 
				associated with	another cell, are labeled ``-1``. The other cell labels
				do not change.

		Returns:
			see :meth:`Tesselation.cell_index`.

		"""
		if isinstance(knn, tuple):
			min_nn, max_nn = knn
		else:
			min_nn, max_nn = knn, None
		points = self.scaler.scale_point(points, inplace=False)
		D = cdist(self.descriptors(points, asarray=True), \
			self._cell_centers, metric, **kwargs)
		ncells = self._cell_centers.shape[0]
		if format == 'force array':
			min_nn = None
			format = 'array' # for later call to :func:`format_cell_index`
		if max_nn or min_nn or min_location_count:
			K = np.argmin(D, axis=1) # cell indices
			nonempty, positive_count = np.unique(K, return_counts=True)
			# max_nn:
			# set K[i] = -1 for all point i in cells that are too large
			if max_nn:
				large, = (max_nn < positive_count).nonzero()
				if large.size:
					for c in nonempty[large]:
						cell = K == c
						I = np.argsort(D[cell, c])
						cell, = cell.nonzero()
						excess = cell[I[max_nn:]]
						K[excess] = -1
			# min_nn:
			# switch to vector-pair representation if any cell is too small
			if min_nn:
				count = np.zeros(ncells, dtype=positive_count.dtype)
				count[nonempty] = positive_count
				small = count < min_nn
				if min_location_count:
					small = np.logical_and(small, min_location_count <= count)
				if np.any(small):
					# small and missing cells
					I = np.argsort(D[:,small], axis=0)[:min_nn].flatten()
					small, = small.nonzero()
					J = np.tile(small, min_nn) # cell indices
					# large-enough cells
					if min_location_count:
						small = count < min_nn
					point_in_small_cells = np.any(
						small[:,np.newaxis] == K[np.newaxis,:], axis=0)
					Ic = np.logical_not(point_in_small_cells)
					Jc = K[Ic]
					Ic, = Ic.nonzero()
					if max_nn:
						Ic = Ic[0 <= Jc]
						Jc = Jc[0 <= Jc]
					#
					K = (np.concatenate((I, Ic)), np.concatenate((J, Jc)))
			# min_location_count:
			# set K[i] = -1 for all point i in cells that are too small
			elif min_location_count:
				excluded_cells = positive_count < min_location_count
				if np.any(excluded_cells):
					for c in nonempty[excluded_cells]:
						K[K == c] = -1
		else:
			K = np.argmin(D, axis=1) # cell indices
		return format_cell_index(K, format=format, select=select,
			shape=(points.shape[0], self.cell_adjacency.shape[0]))

	# cell_centers property
	@property
	def cell_centers(self):
		"""Unscaled coordinates of the cell centers (numpy.ndarray)."""
		if isinstance(self.scaler.factor, pd.Series):
			return self.scaler.unscale_point(pd.DataFrame(self._cell_centers, \
				columns=self.scaler.factor.index))
		else:
			return self.scaler.unscale_point(self._cell_centers)

	@cell_centers.setter
	def cell_centers(self, centers):
		self._cell_centers = self.scaler.scale_point(centers)


class Voronoi(Delaunay):
	"""
	Voronoi graph.

	:class:`Voronoi` explicitly represents the cell boundaries, as a Voronoi graph, on top of the 
	Delaunay graph that connects the cell centers.
	It implements the construction of this additional graph using :class:`scipy.spatial.Voronoi`.
	This default implementation is lazy. If vertices and ridges are available, they are stored in
	private attributes :attr:`_vertices`, :attr:`_vertex_adjacency` and :attr:`_cell_vertices`.
	Otherwise, when `vertices`, `vertex_adjacency` or `cell_vertices` properties are called, the 
	attributes are transparently made available calling the :meth:`_postprocess` private method.
	Memory space can thus be freed again, setting `vertices`, `vertex_adjacency` and `cell_vertices` 
	to ``None``.
	Note however that subclasses may override these on-time calculation mechanics.

	Attributes:

		_vertices (numpy.ndarray): 
			scaled coordinates of the Voronoi vertices.

		_vertex_adjacency (scipy.sparse):
			adjacency matrix for Voronoi vertices.

		_cell_vertices (dict of array-like):
			mapping of cell indices to their associated vertices as indices in 
			:attr:`vertices`.

	"""
	def __init__(self, scaler=Scaler()):
		Delaunay.__init__(self, scaler)
		self._vertices = None
		self._vertex_adjacency = None
		self._cell_vertices = None

	# vertices property
	@property
	def vertices(self):
		"""Unscaled coordinates of the Voronoi vertices (numpy.ndarray)."""
		if self._cell_centers is not None and self._vertices is None:
			self._postprocess()
		if isinstance(self.scaler.factor, pd.Series):
			return self.scaler.unscale_point(pd.DataFrame(self._vertices, \
				columns=self.scaler.factor.index))
		else:
			return self.scaler.unscale_point(self._vertices)

	@vertices.setter
	def vertices(self, vertices):
		self._vertices = self.scaler.scale_point(vertices)

	# cell_adjacency property
	@property
	def cell_adjacency(self):
		if self._cell_centers is not None and self._cell_adjacency is None:
			self._postprocess()
		return self._cell_adjacency

	# whenever you redefine a getter you have to redefine the corresponding setter
	@cell_adjacency.setter # copy/paste
	def cell_adjacency(self, matrix):
		self._cell_adjacency = matrix

	# cell_vertices property
	@property
	def cell_vertices(self):
		if self._cell_centers is not None and self._cell_vertices is None:
			self._postprocess()
		return self._cell_vertices

	@cell_vertices.setter
	def cell_vertices(self, vertex_indices):
		self._cell_vertices = vertex_indices

	# vertex_adjacency property
	@property
	def vertex_adjacency(self):
		if self._cell_centers is not None and self._vertex_adjacency is None:
			self._postprocess()
		return self._vertex_adjacency

	@vertex_adjacency.setter
	def vertex_adjacency(self, matrix):
		self._vertex_adjacency = matrix

	def _postprocess(self):
		"""Compute the Voronoi.

		This private method may be called anytime by :attr:`vertices`, :attr:`vertex_adjacency`
		or :attr:`cell_vertices`.
		"""
		if self._cell_centers is None:
			raise NameError('`cell_centers` not defined; tesselation has not been grown yet')
		else:
			voronoi = spatial.Voronoi(np.asarray(self._cell_centers))
			self._vertices = voronoi.vertices
			self._cell_vertices = { i: np.array([ v for v in voronoi.regions[r] if 0 <= v ]) \
					for i, r in enumerate(voronoi.point_region) if 0 <= r }
			n_centers = self._cell_centers.shape[0]
			# decompose the ridges as valid pairs of vertices and build an adjacency matrix
			ps = []
			for r in voronoi.ridge_vertices:
				pairs = np.c_[r, np.roll(r, 1)]
				pairs = pairs[np.logical_not(np.any(pairs == -1, axis=1))]
				ps.append(pairs)
			ij = np.concatenate(ps)
			n_vertices = self._vertices.shape[0]
			self._vertex_adjacency = sparse.coo_matrix((np.ones(ij.size, dtype=bool),
					(ij.ravel('F'), np.fliplr(ij).ravel('F'))),
				shape=(n_vertices, n_vertices))
			#
			if self._cell_adjacency is None:
				n_ridges = voronoi.ridge_points.shape[0]
				self._cell_adjacency = sparse.csr_matrix((\
					np.tile(np.arange(0, n_ridges, dtype=int), 2), (\
					voronoi.ridge_points.flatten('F'), \
					np.fliplr(voronoi.ridge_points).flatten('F'))), \
					shape=(n_centers, n_centers))
			return voronoi



class RegularMesh(Voronoi):
	"""Regular k-D grid.

	Attributes:
		lower_bound:
		upper_bound:
		count_per_dim:
		min_probability:
		avg_probability:
		max_probability:

	Rather slow. May be reimplemented some day."""
	def __init__(self, scaler=None, lower_bound=None, upper_bound=None, count_per_dim=None, min_probability=None, max_probability=None, avg_probability=None, **kwargs):
		Voronoi.__init__(self) # just ignore `scaler`
		self.lower_bound = lower_bound
		self.upper_bound = upper_bound
		self.count_per_dim = count_per_dim
		self.min_probability = min_probability
		self.max_probability = max_probability
		self.avg_probability = avg_probability

	def tesselate(self, points, **kwargs):
		points = self._preprocess(points)
		if self.lower_bound is None:
	 		self.lower_bound = points.min(axis=0)
		elif isinstance(points, pd.DataFrame) and not isinstance(self.lower_bound, pd.Series):
			self.lower_bound = pd.Series(self.lower_bound, index=points.columns)
		if self.upper_bound is None:
			self.upper_bound = points.max(axis=0)
		elif isinstance(points, pd.DataFrame) and not isinstance(self.upper_bound, pd.Series):
			self.upper_bound = pd.Series(self.upper_bound, index=points.columns)
		if self.count_per_dim is None:
			size = self.upper_bound - self.lower_bound
			if self.avg_probability:
				n_cells = 1.0 / self.avg_probability
			else:
				raise NotImplementedError
			increment = exp(log(np.asarray(size).prod() / n_cells) / points.shape[1])
			if isinstance(size, pd.Series):
				self.count_per_dim = pd.Series.round(size / increment)
			else:
				self.count_per_dim = np.round(size / increment)
		elif isinstance(points, pd.DataFrame) and not isinstance(self.count_per_dim, pd.Series):
			self.count_per_dim = pd.Series(self.count_per_dim, index=points.columns)
		if isinstance(points, pd.DataFrame):
			grid = pd.concat([self.lower_bound, self.upper_bound, self.count_per_dim + 1], axis=1).T
			self.grid = [ np.linspace(*col.values) for _, col in grid.iteritems() ]
		else:
			grid = np.stack((self.lower_bound, self.upper_bound, self.count_per_dim + 1), axis=0)
			self.grid = [ np.linspace(col[0], col[1], int(col[2])) for col in grid.T ]
		cs = np.meshgrid(*[ (g[:-1] + g[1:]) / 2 for g in self.grid ], indexing='ij')
		self._cell_centers = np.column_stack([ c.flatten() for c in cs ])

	def _postprocess(self):
		pass

	# cell_centers property
	@property
	def cell_centers(self):
		return self._cell_centers

	@cell_centers.setter
	def cell_centers(self, centers):
		self._cell_centers = centers

	# vertices property
	@property
	def vertices(self):
		if self._vertices is None:
			vs = np.meshgrid(*self.grid, indexing='ij')
			self._vertices = np.column_stack([ v.flatten() for v in vs ])
		return self._vertices

	@vertices.setter
	def vertices(self, vertices):
		self._vertices = vertices

	# cell_adjacency property
	@property
	def cell_adjacency(self):
		if self._cell_adjacency is None:
			cix = np.meshgrid(*[ np.arange(0, len(g) - 1) for g in self.grid ], \
				indexing='ij')
			cix = np.column_stack([ g.flatten() for g in cix ])
			c2  = np.atleast_2d(np.sum(cix * cix, axis=1))
			self._cell_adjacency = sparse.csr_matrix(\
				np.abs(c2 + c2.T - 2 * np.dot(cix, cix.T) - 1.0) < 1e-6)
		return self._cell_adjacency

	@cell_adjacency.setter # copy/paste
	def cell_adjacency(self, matrix):
		self._cell_adjacency = matrix

	# vertex_adjacency property
	@property
	def vertex_adjacency(self):
		if self._vertex_adjacency is None:
			vix = np.meshgrid(*[ np.arange(0, len(g)) for g in self.grid ], \
				indexing='ij')
			vix = np.column_stack([ g.flatten() for g in vix ])
			v2  = np.atleast_2d(np.sum(vix * vix, axis=1))
			self._vertex_adjacency = sparse.csr_matrix(\
				np.abs(v2 + v2.T - 2 * np.dot(vix, vix.T) - 1.0) < 1e-6)
		return self._vertex_adjacency

	@vertex_adjacency.setter # copy/paste
	def vertex_adjacency(self, matrix):
		self._vertex_adjacency = matrix

	# cell_vertices property
	@property
	def cell_vertices(self):
		if self._cell_vertices is None:
			cs, vs = self.cell_centers, self.vertices
			c2 = np.atleast_2d(np.sum(cs * cs, axis=1))
			v2 = np.atleast_2d(np.sum(vs * vs, axis=1))
			d2 = np.sum((cs[0] - vs[0]) ** 2)
			self._cell_vertices = sparse.dok_matrix(\
				np.abs(c2.T + v2 - 2 * np.dot(cs, vs.T) - d2) < 1e-6)
			#assert self._cell_vertices.tocsr() == dict_to_sparse(sparse_to_dict(self._cell_vertices), shape=self._cell_vertices.shape)
			self._cell_vertices = sparse_to_dict(self._cell_vertices)
		return self._cell_vertices

	@cell_vertices.setter
	def cell_vertices(self, matching):
		self._cell_vertices = matching



def dict_to_sparse(cell_vertex, shape=None):
	"""
	Convert cell-vertex association :class:`dict`s to :mod:`~scipy.sparse` matrices.
	"""
	if not sparse.issparse(cell_vertex):
		if shape:
			n_cells = shape[0]
			args = [shape]
		else:
			n_cells = max(cell_vertex.keys())
			args = []
		indices = [ cell_vertex.get(c, []) for c in range(n_cells) ]
		indptr = np.r_[0, np.cumsum([ len(list(vs)) for vs in indices ])]
		indices = np.asarray(list(itertools.chain(*indices)))
		cell_vertex = sparse.csr_matrix((np.ones(indices.size, dtype=bool), indices, indptr),
			*args)
	return cell_vertex

def sparse_to_dict(cell_vertex):
	"""
	Convert cell-vertex associations :mod:`~scipy.sparse` matrices to :class:`dict`s.
	"""
	if sparse.issparse(cell_vertex):
		matrix = cell_vertex.tocsr()
		cell_vertex = { i: matrix.indices[matrix.indptr[i]:matrix.indptr[i+1]] \
				for i in range(matrix.shape[0]) }
	return cell_vertex

