#!/usr/bin/env python

import sys, os, time
sys.path.append(os.getcwd() + "/..")
sys.path.append(os.getcwd() + "/../../common")
from model import *
import numpy as np
from numpy import linalg

from h5 import HDFArchive
from triqs.utility import mpi
from triqs_ctseg import Solver, version

# --------- Construct the CTSEG solver ----------
constr_params = {
        'beta' : beta,
        'gf_struct' : gf_struct,
        'n_tau' : 10001
        }
S = Solver(**constr_params)

# --- We need to rotate G0_iw into the local eigenbasis
def get_h0_Delta(G_iw):
    """
    This function extracts the h_0 as well as Delta(iw) component
    for a BlockGf G_iw of the form 1/(iw - h_0 - Delta(iw))
    """
    assert isinstance(G_iw, BlockGf)
    h0_lst, Delta_iw = [], G_iw.copy()
    for bl in G_iw.indices:
        Delta_iw[bl] << iOmega_n - inverse(G_iw[bl])
        tail, err = fit_hermitian_tail(Delta_iw[bl])
        Delta_iw[bl] << Delta_iw[bl] - tail[0]
        h0_lst.append(tail[0])
    return h0_lst, Delta_iw

# Get the rotations to the eigenbasis for each block of G0_iw
h0, Delta_iw = get_h0_Delta(G0_iw)
rot_lst = [np.matrix(linalg.eig(h0_bl)[1]) for h0_bl in h0]
# Compute chemical potential 
chem_pot = []
for h0_bl in h0:
    chem_pot += [-l for l in linalg.eig(h0_bl)[0].real]
    

# Rotate Delta_iw
for (bl, g0_bl), rot_bl in zip(Delta_iw, rot_lst):
    g0_bl << rot_bl.H * g0_bl * rot_bl

# --------- Initialize G0_iw ----------
S.Delta_tau << Fourier(Delta_iw)

# --------- Solve! ----------
solve_params = {
        'h_int' : h_int,
        'n_warmup_cycles' : 10000,
        'n_cycles' : 1000000,
        'length_cycle' : 100,
        "hartree_shift": chem_pot
        }
start = time.time()
S.solve(**solve_params)
end = time.time()

# Rotate back G_tau
for (bl, g_bl), rot_bl in zip(S.results.G_tau, rot_lst):
    g_bl << rot_bl * g_bl * rot_bl.H


# -------- Save in archive ---------
if mpi.is_master_node():
    with HDFArchive("../results/ctseg_J.h5",'w') as results:
        G_iw = BlockGf(mesh=iw_mesh, gf_struct=gf_struct)
        for bl, l in gf_struct:
            tail = make_zero_tail(G_iw[bl], 3)
            tail[1] = np.eye(l)
            G_iw[bl] << Fourier(S.results.G_tau[bl], tail)
        results["G"] = G_iw

        import inspect
        import __main__
        results.create_group("Solver_Info")
        info_grp = results["Solver_Info"]
        info_grp["solver_name"] = "triqs_ctseg"
        info_grp["constr_params"] = constr_params
        info_grp["solve_params"] = solve_params
        # info_grp["solver"] = S
        info_grp["solver_version"] = version.version
        info_grp["solver_git_hash"] = version.triqs_ctseg_hash
        info_grp["triqs_git_hash"] = version.triqs_hash
        info_grp["script"] = inspect.getsource(__main__)
        info_grp["num_threads"] = mpi.size
        info_grp["run_time"] = end - start
