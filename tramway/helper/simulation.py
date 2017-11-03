# -*- coding: utf-8 -*-

# Copyright © 2017, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

import numpy as np
import pandas as pd


def random_walk(diffusivity=None, force=None, \
		trajectory_mean_count=100, trajectory_count_sd=3, turn_over=.1, \
		box=(0., 0., 1., 1.), duration=10., time_step=.05, \
		full=False):
	_box = np.asarray(box)
	dim = _box.size / 2
	support_lower_bound = _box[:dim]
	support_size = _box[dim:]
	# default maps
	def null_scalar_map(xy, t):
		return 0.
	def null_vector_map(xy, t):
		return np.zeros((dim,))
	if diffusivity is None:
		diffusivity = null_scalar_map
	if force is None:
		force = null_vector_map
	# 
	N = int(round(float(duration) / time_step))
	K = np.round(np.random.randn(N) * trajectory_count_sd + trajectory_mean_count)
	T = np.arange(time_step, duration + time_step, time_step)
	if K[1] < K[0]: # switch so that K[0] <= K[1]
		tmp = K[0]
		K[0] = K[1]
		K[1] = tmp
	if K[-2] < K[-1]: # switch so that K[end-1] >= K[end]
		tmp = K[-1]
		K[-1] = K[-2]
		K[-2] = tmp
	xs = []
	X = np.array([])
	knew = n0 = 0
	for t, k in zip(T, K):
		k = int(k)
		if t == duration:
			kupdate = k
		elif X.size:
			kupdate = max(knew, int(round(min(k, X.shape[0]) * (1. - turn_over))))
		else:
			kupdate = 0
		knew = k - kupdate
		if knew == 0:
			if not X.size:
				raise RuntimeError
			Xnew = np.zeros((knew, dim), dtype=X.dtype)
			nnew = np.zeros((knew, ), dtype=n.dtype)
		else:
			Xnew = np.random.rand(knew, dim) * support_size + support_lower_bound
			nnew = np.arange(n0, n0 + knew)
			n0 += knew
		if X.size:
			X = X[:kupdate]
			D, F = zip(*[ (diffusivity(x, t), force(x, t)) for x in X ])
			D, F = np.array(D), np.array(F)
			dX = F + np.sqrt(2. * D.reshape(D.size, 1)) * np.random.randn(*X.shape)
			X = np.concatenate((Xnew, X + dX))
			n = np.concatenate((nnew, n[:kupdate]))
		else:
			X = Xnew
			n = nnew
		if np.unique(n).size < n.size:
			print((n, kupdate, knew, t))
			raise RuntimeError
		xs.append(np.concatenate((n.reshape(n.size, 1), X, np.full((n.size, 1), t)), axis=1))
	columns = 'xyz'
	if dim <= 3:
		columns = [ d for d in columns[:dim] ]
	else:
		columns = [ 'x'+str(i) for i in range(dim) ]
	columns = ['n'] + columns + ['t']
	data = np.concatenate(xs, axis=0)
	data = data[np.lexsort((data[:,-1], data[:,0]))]
	points = pd.DataFrame(data=data, columns=columns)
	if not full:
		points = crop(points, _box)
	return points


def crop(points, box):
	box = np.asarray(box)
	dim = box.size / 2
	support_lower_bound = box[:dim]
	support_size = box[dim:]
	support_upper_bound = support_lower_bound + support_size
	coord_cols = [ c for c in points.columns if c not in ['n', 't'] ]
	within = np.all(np.logical_and(support_lower_bound <= points[coord_cols].values,
		points[coord_cols].values <= support_upper_bound), axis=1)
	points = points.copy()
	points['n'] += np.cumsum(np.logical_not(within), dtype=points.index.dtype)
	single_point = 0 < points['n'].diff().values
	#single_point[1:-1] &= single_point[2:]
	single_point[1:-1] = np.logical_and(single_point[1:-1], single_point[2:])
	ok = np.logical_not(single_point)
	points = points.iloc[ok]
	within = within[ok]
	points['n'] -= (points['n'].diff() - 1).clip_lower(0).cumsum()
	points = points.iloc[within]
	points.index = np.arange(points.shape[0])
	return points


def truth(cells, t=None, diffusivity=None, force=None):
	dim = cells.cells[0].center.size
	I, DF = [], []
	for i in cells.cells:
		cell = cells.cells[i]
		I.append(i)
		if diffusivity is None:
			D = []
		else:
			D = [diffusivity(cell.center, t)]
		if force is None:
			F = []
		else:
			F = force(cell.center, t)
		DF.append(np.concatenate((D, F)))
	DF = np.vstack(DF)
	if diffusivity is None:
		columns = []
	else:
		columns = [ 'diffusivity' ]
	if force is not None:
		columns += [ 'force x' + str(col+1) for col in range(dim) ]
	return pd.DataFrame(index=I, data=DF, columns = columns)

