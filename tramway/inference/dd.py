# -*- coding: utf-8 -*-

# Copyright © 2017, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


from .base import *
from warnings import warn
from math import pi, log
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from collections import OrderedDict


setup = {'arguments': OrderedDict((
		('localization_error',	('-e', dict(type=float, default=0.01, help='localization error'))),
		('diffusivity_prior',	('-d', dict(type=float, default=0.01, help='prior on the diffusivity'))),
		('jeffreys_prior',	('-j', dict(action='store_true', help="Jeffreys' prior"))),
		('min_diffusivity',	dict(type=float, default=0, help='minimum diffusivity value allowed')))),
		'cell_sampling': 'group'}


def dd_neg_posterior(diffusivity, cells, square_localization_error, diffusivity_prior, jeffreys_prior, \
		dt_mean, min_diffusivity=0):
	"""
	Adapted from InferenceMAP's *dDDPosterior* procedure::

		for (int a = 0; a < NUMBER_OF_ZONES; a++) {
			ZONES[a].gradDx = dvGradDx(DD,a);
			ZONES[a].gradDy = dvGradDy(DD,a);
			ZONES[a].priorActive = true;
		}

		for (int z = 0; z < NUMBER_OF_ZONES; z++) {
			const double gradDx = ZONES[z].gradDx;
			const double gradDy = ZONES[z].gradDy;
			const double D = DD[z];

			for (int j = 0; j < ZONES[z].translocations; j++) {
				const double dt = ZONES[z].dt[j];
				const double dx = ZONES[z].dx[j];
				const double dy = ZONES[z].dy[j];
				const double Dnoise = LOCALIZATION_ERROR*LOCALIZATION_ERROR/dt;

				result += - log(4.0*PI*(D + Dnoise)*dt) - ( dx*dx + dy*dy)/(4.0*(D+Dnoise)*dt);
			}

			if (ZONES[z].priorActive == true) {
				result -= D_PRIOR*(gradDx*gradDx*ZONES[z].areaX + gradDy*gradDy*ZONES[z].areaY);
				if (JEFFREYS_PRIOR == 1) {
					result += 2.0*log(D) - 2.0*log(D*ZONES[z].dtMean + LOCALIZATION_ERROR*LOCALIZATION_ERROR);
				}
			}
		}

		return -result;

	"""
	observed_min = np.min(diffusivity)
	if observed_min < min_diffusivity and not np.isclose(observed_min, min_diffusivity):
		warn(DiffusivityWarning(observed_min, min_diffusivity))
	noise_dt = square_localization_error
	j = 0
	result = 0.0
	for i in cells:
		cell = cells[i]
		n = len(cell)
		# posterior calculations
		if cell.cache['dxy2'] is None:
			cell.cache['dxy2'] = np.sum(cell.dxy * cell.dxy, axis=1) # dx**2 + dy**2 + ..
		D_dt = 4.0 * (diffusivity[j] * cell.dt + noise_dt) # 4*(D+Dnoise)*dt
		result += n * log(pi) + np.sum(np.log(D_dt)) # sum(log(4*pi*Dtot*dt))
		result += np.sum(cell.cache['dxy2'] / D_dt) # sum((dx**2+dy**2+..)/(4*Dtot*dt))
		# prior
		if diffusivity_prior:
			area = cells.grad_sum(i)
			# gradient of diffusivity
			gradD = cells.grad(i, diffusivity)
			if gradD is None:
				#raise RuntimeError('missing gradient')
				continue
			result += diffusivity_prior * np.dot(gradD * gradD, area)
		j += 1
	if jeffreys_prior:
		result += 2.0 * np.sum( log(diffusivity * dt_mean + square_localization_error) - \
					log(diffusivity) )
	return result

def inferDD(cells, localization_error=0.0, diffusivity_prior=None, jeffreys_prior=None, \
		min_diffusivity=0, **kwargs):
	# initialize the diffusivity array and the caches
	initial = []
	for i in cells:
		cell = cells[i]
		# sanity checks
		if not bool(cell):
			raise ValueError('empty cell at index: {}'.format(i))
		if not np.all(0 < cell.dt):
			warn('translocation dts are not all positive', RuntimeWarning)
			cell.dxy[cell.dt < 0] *= -1.
			cell.dt[ cell.dt < 0] *= -1.
		# initialize the cache
		cell.cache = dict(dxy2=None)
		# initialize the local diffusivity parameter
		dt_mean_i = np.mean(cell.dt)
		initial.append((dt_mean_i, \
			np.mean(cell.dxy * cell.dxy) / (2.0 * dt_mean_i)))
	dt_mean, initialD = (np.array(xs) for xs in zip(*initial))
	# parametrize the optimization procedure
	if min_diffusivity is not None:
		kwargs['bounds'] = [(min_diffusivity,None)] * initialD.size
	# run the optimization
	sq_loc_err = localization_error * localization_error
	result = minimize(dd_neg_posterior, initialD,
		args=(cells, sq_loc_err, diffusivity_prior, jeffreys_prior, dt_mean, min_diffusivity),
		**kwargs)
	# format the optimal diffusivity array
	index = np.array(list(cells.keys()))
	return pd.DataFrame(data=result.x[:,np.newaxis], index=index, columns=['diffusivity'])

