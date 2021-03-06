# -*- coding:utf-8 -*-

# Copyright © 2017-2019, Institut Pasteur
#    Contributor: Maxime Duval

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

"""
Useful functions
"""

import glob
import pickle
import os

import tqdm
import pandas as pd


def extract_i(file):
    """Extracts the id of a file generated by the cluster."""
    return file.split('\\')[3].split('_')[2].split('.')[0]


def concat_job_files(job_name, output_dir, output_name, get_rws=True,
                     df_path='Y:\data\df', dict_path='Y:\data\dict',
                     rw_path='Y:\data\rws'):
    """Concatenates and deletes files produced by single jobs when doing a
    batch array of jobs.
    """
    dfs = []
    prms = {}
    rws = []
    rws_paths = glob.glob(f'{rw_path}\df_{job_name}_*')
    df_paths = glob.glob(f'{df_path}\df_{job_name}_*')
    dict_paths = glob.glob(f'{dict_path}\dict_{job_name}_*')
    for rw_path, df_path, dict_path in tqdm.tqdm_notebook(
            zip(rws_paths, df_paths, dict_paths), total=len(df_paths)):
        try:
            if get_rws:
                rws.append(pd.read_csv(rw_path, index_col=0))
                os.remove(rw_path)
            dfs.append(pd.read_csv(df_path, index_col=0))
            with open(dict_path, 'rb') as handle:
                dict_i = pickle.load(handle)
            prms = {**prms, **dict_i}
            os.remove(df_path)
            os.remove(dict_path)
        except:
            print(f'Could not add file {extract_i(df_path)}')
    df = pd.concat(dfs, sort=True).reset_index()
    if get_rws:
        rws = pd.concat(rws).reset_index()
        rws.to_feather(f'{output_dir}\\RWs_{output_name}.feather')
    df.to_feather(f'{output_dir}\\features_{output_name}.feather')
    with open(f'{output_dir}\\prms_{output_name}.pickle', 'wb') as f:
        pickle.dump(prms, f)


def load(Dir, name, trajs=True):
    """Loads files associated with a job array (of producing random walk
    features). Returns parameters of the generated random walks, a DataFrame,
    and possibly raw trajectories.
    """
    path = f'{Dir}\\features_{name}.feather'
    df_feat = pd.read_feather(path)
    with open(f'{Dir}\\prms_{name}.pickle', 'rb') as f:
        prms = pickle.load(f)
    if trajs:
        RWs = pd.read_feather(f'{Dir}\\RWs_{name}.feather')
        return prms, df_feat, RWs
    else:
        return prms, df_feat
