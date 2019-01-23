# -*- coding: utf-8 -*-

# Copyright © 2018, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


from .base import *
from .dv import DV
from .optimization import *
from warnings import warn
from math import pi, log
import numpy as np
import pandas as pd
import scipy.sparse as sparse
from collections import OrderedDict
import time
from scipy.stats import trim_mean


setup = {'name': ('stochastic.dv', 'stochastic.dv1'),
    'provides': 'dv',
    'infer': 'infer_stochastic_DV',
    'arguments': OrderedDict((
        ('localization_error',  ('-e', dict(type=float, help='localization precision (see also sigma; default is 0.03)'))),
        ('diffusivity_prior',   ('-d', dict(type=float, help='prior on the diffusivity'))),
        ('potential_prior',     ('-v', dict(type=float, help='prior on the potential'))),
        ('jeffreys_prior',      ('-j', dict(action='store_true', help="Jeffreys' prior"))),
        ('time_prior',          ('-t', dict(type=float, help='prior on the time'))),
        ('min_diffusivity',     dict(type=float, help='minimum diffusivity value allowed')),
        ('max_iter',            dict(type=int, help='maximum number of iterations')),
        ('compatibility',       ('-c', '--inferencemap', '--compatible',
                                dict(action='store_true', help='InferenceMAP compatible'))),
        ('epsilon',             ('--grad-epsilon', dict(args=('--eps',), kwargs=dict(type=float, help='if defined, every spatial gradient component can recruit all of the neighbours, minus those at a projected distance less than this value'), translate=True))),
        ('grad_selection_angle',('-a', dict(type=float, help='top angle of the selection hypercone for neighbours in the spatial gradient calculation (1= pi radians; if not -c, default is: {})'.format(default_selection_angle)))),
        ('grad',                dict(help="spatial gradient implementation; any of 'grad1', 'gradn'")),
        ('export_centers',      dict(action='store_true')),
        ('verbose',             ()))),
        #('region_size',         ('-s', dict(type=int, help='radius of the regions, in number of adjacency steps'))))),
    'cell_sampling': 'group'}


class LocalDV(DV):
    __slots__ = ('regions','prior_delay','_n_calls')

    def __init__(self, diffusivity, potential, diffusivity_prior=None, potential_prior=None,
        minimum_diffusivity=None, positive_diffusivity=None, prior_include=None,
        regions=None, prior_delay=None):
        # positive_diffusivity is for backward compatibility
        DV.__init__(self, diffusivity, potential, diffusivity_prior, potential_prior,
            minimum_diffusivity, positive_diffusivity, prior_include)
        self.regions = regions
        self.prior_delay = prior_delay
        self._n_calls = 0.

    def region(self, i):
        return self.regions[i]

    def indices(self, cell_ids):
        if isinstance(cell_ids, (int, np.int_)):
            return np.array([ cell_ids, int(self.combined.size / 2) + cell_ids ])
        cell_ids = np.array(cell_ids)
        cell_ids.sort()
        return np.concatenate((cell_ids, int(self.combined.size / 2) + cell_ids))
    def diffusivity_indices(self, cell_ids):
        if isinstance(cell_ids, (int, np.int_)):
            cell_ids = [cell_ids]
        return np.array(cell_ids)
    def potential_indices(self, cell_ids):
        if isinstance(cell_ids, (int, np.int_)):
            cell_ids = [cell_ids]
        return int(self.combined.size / 2) + np.array(cell_ids)

    def potential_prior(self, i):
        if self.prior_delay:
            if self._n_calls < self.prior_delay:
                prior = None
            else:
                prior = DV.potential_prior(self, i)
            if self._diffusivity_prior:
                self._n_calls += .5
            else:
                self._n_calls += 1.
        else:
                prior = DV.potential_prior(self, i)
        return prior

    def diffusivity_prior(self, i):
        if self.prior_delay:
            if self._n_calls < self.prior_delay:
                prior = None
            else:
                prior = DV.diffusivity_prior(self, i)
            if self._potential_prior:
                self._n_calls += .5
            else:
                self._n_calls += 1.
        else:
                prior = DV.diffusivity_prior(self, i)
        return prior


def make_regions(cells, index, reverse_index, size=1):
    A = cells.adjacency
    regions = []
    for i in index:
        j = set([i.tolist()])
        j_inner = set()
        for k in range(size):
            j_outer = j - j_inner
            j_inner = j
            for l in j_outer:
                neighbours = A.indices[A.indptr[l]:A.indptr[l+1]] # NOT cells.neighbours(l)
                j |= set(neighbours.tolist())
        j = reverse_index[list(j)]
        regions.append(j)
    return regions


def local_dv_neg_posterior(j, x, dv, cells, sigma2, jeffreys_prior,
    time_prior, dt_mean, index, reverse_index, grad_kwargs,
    posterior_info=None, y0=0., iter_num=None, verbose=False):
    """
    """

    # extract `D` and `V`
    #dv.update(x)
    #D = dv.D # slow(?)
    #V = dv.V
    #Dj = D[j]
    Dj = x[j]
    if np.isnan(Dj):
        raise ValueError('D is nan')
    V = x[int(x.size/2):]
    #

    noise_dt = sigma2

    # for all cell
    i = index[j]
    cell = cells[i]
    n = len(cell) # number of translocations

    # spatial gradient of the local potential energy
    gradV = cells.grad(i, V, reverse_index, **grad_kwargs)
    #print('{}\t{}\t{}\t{}\t{}\t{}'.format(i+1,D[j], V[j], -gradV[0], -gradV[1], result))
    #print('{}\t{}\t{}'.format(i+1, *gradV))
    if gradV is None or np.any(np.isnan(gradV)):
        raise ValueError('gradV is not defined')

    # various posterior terms
    #print(cell.dt)
    D_dt = Dj * cell.dt
    denominator = 4. * (D_dt + noise_dt)
    if np.any(denominator <= 0):
        raise ValueError('undefined posterior; local diffusion value: %s', Dj)
    dr_minus_drift = cell.dr + np.outer(D_dt, gradV)
    # non-directional squared displacement
    ndsd = np.sum(dr_minus_drift * dr_minus_drift, axis=1)
    raw_posterior = n * log(pi) + np.sum(np.log(denominator)) + np.sum(ndsd / denominator)

    if np.isnan(raw_posterior):
        raise ValueError('undefined posterior; local diffusion value: %s', Dj)

    # priors
    standard_priors, time_priors = 0., 0.
    potential_prior = dv.potential_prior(j)
    if potential_prior:
        standard_priors += potential_prior * cells.grad_sum(i, gradV * gradV, reverse_index)
    diffusivity_prior = dv.diffusivity_prior(j)
    if diffusivity_prior:
        D = x[:int(x.size/2)]
        # spatial gradient of the local diffusivity
        gradD = cells.grad(i, D, reverse_index, **grad_kwargs)
        if gradD is not None:
            # `grad_sum` memoizes and can be called several times at no extra cost
            standard_priors += diffusivity_prior * cells.grad_sum(i, gradD * gradD, reverse_index)
    #print('{}\t{}\t{}'.format(i+1, D[j], result))
    if jeffreys_prior:
        if Dj <= 0:
            raise ValueError('non positive diffusivity')
        standard_priors += jeffreys_prior * 2. * np.log(Dj * dt_mean[j] + sigma2) - np.log(Dj)

    if time_prior:
        if diffusivity_prior:
            dDdt = cells.time_derivative(i, D, reverse_index)
            # assume fixed-duration time window
            time_priors += diffusivity_prior * time_prior * dDdt * dDdt
        if potential_prior:
            dVdt = cells.time_derivative(i, V, reverse_index)
            time_priors += potential_prior * time_prior * dVdt * dVdt

    priors = standard_priors + time_priors
    result = raw_posterior + priors
    #if 1e6 < np.max(np.abs(gradV)):
    #    print((i, raw_posterior, standard_priors, Dj, V[j], n, gradV, [V[_j] for _j in cells.neighbours(i)]))

    if verbose:
        print((i, raw_posterior, standard_priors, time_priors))
    if posterior_info is not None:
        if iter_num is None:
            info = [i, raw_posterior, result]
        else:
            info = [iter_num, i, raw_posterior, result]
        posterior_info.append(info)

    return result - y0


def infer_stochastic_DV(cells, diffusivity_prior=None, potential_prior=None, time_prior=None,
    prior_delay=None, jeffreys_prior=False, min_diffusivity=None, max_iter=None,
    epsilon=None, grad_selection_angle=None, compatibility=False,
    export_centers=False, verbose=True, superlocal=False, stochastic=True, x0=None,
    return_struct=False,
    **kwargs):
    """
    See also :func:`~tramway.inference.optimization.minimize_sparse_bfgs`.
    """

    # initial values
    if stochastic and not superlocal and not potential_prior:
        raise ValueError('regularization is required for the potential energy')
    index, reverse_index, n, dt_mean, D_initial, _min_diffusivity, D_bounds, border = \
        smooth_infer_init(cells, min_diffusivity=min_diffusivity, jeffreys_prior=jeffreys_prior)
    # validate or undo some values returned by `smooth_infer_init`
    if jeffreys_prior:
        min_diffusivity = _min_diffusivity
    elif min_diffusivity is None:
        D_bounds = [(None, None)] * D_initial.size
    # V initial values
    if x0 is None:
        try:
            if compatibility:
                raise Exception # skip to the except block
            volume = [ cells[i].volume for i in index ]
        except:
            V_initial = -np.log(n / np.max(n))
        else:
            density = n / np.array([ np.inf if v is None else v for v in volume ])
            density[density == 0] = np.min(density[0 < density])
            V_initial = np.log(np.max(density)) - np.log(density)
    else:
        if x0.size != 2 * D_initial.size:
            raise ValueError('wrong size for x0')
        D_initial, V_initial = x0[:int(x0.size/2)], x0[int(x0.size/2):]

    dv = LocalDV(D_initial, V_initial, diffusivity_prior, potential_prior, min_diffusivity,
        prior_delay=prior_delay)
    posterior_info = []

    # gradient options
    grad_kwargs = {}
    if epsilon is not None:
        if compatibility:
            warn('epsilon breaks backward compatibility with InferenceMAP', RuntimeWarning)
        if grad_selection_angle:
            warn('grad_selection_angle is not compatible with epsilon and will be ignored', RuntimeWarning)
        grad_kwargs['eps'] = epsilon
    else:
        if grad_selection_angle:
            if compatibility:
                warn('grad_selection_angle breaks backward compatibility with InferenceMAP', RuntimeWarning)
        else:
            grad_selection_angle = default_selection_angle
        if grad_selection_angle:
            grad_kwargs['selection_angle'] = grad_selection_angle
    # bounds
    V_bounds = [(0., None)] * V_initial.size
    #if min_diffusivity is not None:
    #    assert np.all(min_diffusivity < D_initial)
    bounds = D_bounds + V_bounds

    # posterior function input arguments
    localization_error = cells.get_localization_error(kwargs, 0.03, True)
    if jeffreys_prior is True:
        jeffreys_prior = 1.
    args = (dv, cells, localization_error, jeffreys_prior, time_prior, dt_mean,
        index, reverse_index, grad_kwargs, posterior_info)

    m = len(index)
    if not stochastic:
        y0 = sum( local_dv_neg_posterior(j, dv.combined, *args[:-1]) for j in range(m) )
        if verbose:
            print('At X0\tactual posterior= {}\n'.format(y0))
        args = args + (y0,)

    # keyword arguments to `minimize_sparse_bfgs`
    sbfgs_kwargs = dict(kwargs)

    # cell groups (a given cell + its neighbours)
    dv.regions = make_regions(cells, index, reverse_index)

    # covariates and subspaces
    if stochastic:
        component = m
        covariate = dv.region
        #covariate = lambda i: np.unique(np.concatenate([ dv.region(_i) for _i in dv.region(i) ]))
        descent_subspace = None
        if superlocal:
            gradient_subspace = dv.indices
            #if 'ls_failure_rate' not in sbfgs_kwargs:
            #    sbfgs_kwargs['ls_failure_rate'] = .9
        else:
            def gradient_subspace(i):
                return np.r_[dv.diffusivity_indices(i), dv.potential_indices(dv.region(i))]
        def fix_linesearch(i, x):
            _r = dv.region(i)
            x[dv.diffusivity_indices(i)] = min(x[dv.diffusivity_indices(i)], trim_mean(x[dv.diffusivity_indices(_r)], .25))
            x[dv.potential_indices(i)] = min(x[dv.potential_indices(i)], trim_mean(x[dv.potential_indices(_r)], .25))
        sbfgs_kwargs['fix_ls'] = fix_linesearch
        if 'fix_ls_trigger' not in sbfgs_kwargs:
            sbfgs_kwargs['fix_ls_trigger'] = 3

        #def gradient_subspace(i):
        #    return np.r_[dv.diffusivity_indices(dv.region(i)), dv.potential_indices(covariate(i))]
    else:
        if superlocal:
            raise ValueError('`stochastic=False` and `superlocal=True` are incompatible')
        component = lambda k: 0
        covariate = lambda i: range(m)
        descent_subspace = None
        gradient_subspace = None
        def col2rows(j):
            i = j % m
            return dv.region(i)
        sbfgs_kwargs['gradient_covariate'] = col2rows

    # other arguments
    if verbose:
        sbfgs_kwargs['verbose'] = verbose
    if max_iter:
        sbfgs_kwargs['max_iter'] = max_iter
    if bounds is not None:
        sbfgs_kwargs['bounds'] = bounds
    if 'eps' not in sbfgs_kwargs:
        sbfgs_kwargs['eps'] = 1. # beware: not the `tramway.inference.grad` option
    # TODO: in principle `superlocal` could work in quasi-Newton work but did not with random `x0`
    sbfgs_kwargs['newton'] = newton = sbfgs_kwargs.get('newton', not stochastic)# or superlocal)
    if newton:
        default_step_max = 1.
        default_wolfe = (.5, None)
    else:
        default_step_max = .5
        default_wolfe = (.1, None)
    if stochastic:
        sbfgs_kwargs['ls_wolfe'] = sbfgs_kwargs.get('ls_wolfe', default_wolfe)
        sbfgs_kwargs['ls_step_max'] = sbfgs_kwargs.get('ls_step_max', default_step_max)
    if 'ls_armijo_max' not in sbfgs_kwargs:
        sbfgs_kwargs['ls_armijo_max'] = 5
    ls_step_max_decay = sbfgs_kwargs.get('ls_step_max_decay', None)
    if ls_step_max_decay:
        sbfgs_kwargs['ls_step_max_decay'] /= float(m)
    if 'ftol' not in sbfgs_kwargs:
        sbfgs_kwargs['ftol'] = 1e-2

    # run the optimization routine
    result = minimize_sparse_bfgs(local_dv_neg_posterior, dv.combined, component, covariate,
            gradient_subspace, descent_subspace, args, **sbfgs_kwargs)
    #if not (result.success or verbose):
    #    warn('{}'.format(result.message), OptimizationWarning)

    # extract the different types of parameters
    dv.update(result.x)
    D, V = dv.D, dv.V
    #if np.any(V < 0):
    #    V -= np.min(V)
    DVF = pd.DataFrame(np.stack((D, V), axis=1), index=index,
        columns=['diffusivity', 'potential'])

    # derivate the forces
    index_, F = [], []
    for i in index:
        gradV = cells.grad(i, V, reverse_index, **grad_kwargs)
        if gradV is not None:
            index_.append(i)
            F.append(-gradV)
    if F:
        F = pd.DataFrame(np.stack(F, axis=0), index=index_,
            columns=[ 'force ' + col for col in cells.space_cols ])
    else:
        warn('not any cell is suitable for evaluating the local force', RuntimeWarning)
        F = pd.DataFrame(np.zeros((0, len(cells.space_cols)), dtype=V.dtype),
            columns=[ 'force ' + col for col in cells.space_cols ])
    DVF = DVF.join(F)

    # add extra information if required
    if export_centers:
        xy = np.vstack([ cells[i].center for i in index ])
        DVF = DVF.join(pd.DataFrame(xy, index=index,
            columns=cells.space_cols))
        #DVF.to_csv('results.csv', sep='\t')

    # format the posteriors
    if posterior_info:
        cols = ['cell', 'fit', 'total']
        if len(posterior_info[0]) == 4:
            cols = ['iter'] + cols
        posterior_info = pd.DataFrame(np.array(posterior_info), columns=cols)

    info = dict(posterior_info=posterior_info)
    if return_struct:
        # cannot be rwa-stored
        info['result'] = result
    else:
        for src_attr in ('resolution',
                'niter',
                ('f', 'f_history'),
                ('projg', 'projg_history'),
                ('err', 'error'),
                ('diagnosis', 'diagnoses')):
            if isinstance(src_attr, str):
                dest_attr = src_attr
            else:
                src_attr, dest_attr = src_attr
            val = getattr(result, src_attr)
            if val is not None:
                info[dest_attr] = val
    return DVF, info

    return DVF, posterior_info

