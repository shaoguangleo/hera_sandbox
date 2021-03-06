#!/usr/bin/env python2.7
"""
skynpz2calfits.py
---------------

convert sky_image.py calibration
solution output in .npz format
(originally from CASA .cal/ tables)
into pyuvdata .calfits format

Nicholas Kern
Dec. 2017
"""
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
from pyuvdata import UVCal, UVData
import numpy as np
import argparse
import os
import scipy.signal as signal
from sklearn import gaussian_process as gp
import copy
from make_calfits import make_calfits

a = argparse.ArgumentParser(description="Turn CASA calibration solutions in {}.npz files from sky_image.py script into .calfits files")

# Required Parameters
a.add_argument("--fname", type=str, help="output calfits filename.", required=True)
a.add_argument("--uv_file", type=str, help="Path to original miriad uv file of data.", required=True)
# Delay Solution Parameters
a.add_argument("--dly_files", type=str, default=None, nargs='*', help="Path to .npz file(s) with antenna delay output from sky_image.py (CASA K cal)")
a.add_argument("--TTonly", default=False, action="store_true", help="only store Tip-Tilt slopes of delay solution.")
a.add_argument("--plot_dlys", default=False, action="store_true", help="plot delay solutions across array.")
# Phase Solution Parameters
a.add_argument("--phs_files", type=str, default=None, nargs='*', help="Path to .npz file(s) with phase output from sky_image.py (CASA G phscal)")
a.add_argument("--plot_phs", default=False, action="store_true", help="plot phase solutions across array.")
# Amplitude Solution Parameters
a.add_argument("--amp_files", type=str, default=None, nargs='*',  help="Path to .npz file(s) with amplitude output from sky_image.py (CASA G ampcal)")
a.add_argument("--plot_amp", default=False, action='store_true', help='plot amp solution across array.')
a.add_argument("--gain_amp_antavg", default=False, action='store_true', help="average gain amplitudes across antennas")
# Bandpass Solution Parameters
a.add_argument("--bp_files", type=str, default=None, nargs='*', help="Path to .npz file(s) with antenna complex bandpass output from sky_image.py (CASA bandpass)")
a.add_argument("--bp_flag_frac", type=float, default=0.5, help="at each freq bin, fraction of antennas flagged needed to broadcast flag to all ants.")
a.add_argument("--bp_broad_flags", default=False, action='store_true', help="broadcast flags at freq channels that satisfy bp_flag_frac")
a.add_argument("--noBPamp", default=False, action='store_true', help="set BP amplitude solutions to zero.")
a.add_argument("--noBPphase", default=False, action='store_true', help="set BP phase solutions to zero.")
a.add_argument('--bp_medfilt', default=False, action='store_true', help="median filter bandpass solutions")
a.add_argument('--medfilt_flag', default=False, action='store_true', help='use median filter to flag bad BP solutions in frequency')
a.add_argument('--medfilt_kernel', default=7, type=int, help="kernel size (channels) for BP median filter")
a.add_argument('--bp_amp_antavg', default=False, action='store_true', help="average bandpass amplitudes across antennas")
a.add_argument('--bp_TTonly', default=False, action='store_true', help="use only tip-tilt phase mode in bandpass solution")
a.add_argument('--plot_bp', default=False, action='store_true', help="plot final bandpass solutions")
a.add_argument('--bp_gp_smooth', default=False, action='store_true', help='smooth bandpass w/ gaussian process. Recommended to precede w/ bp_medfilt.')
a.add_argument('--bp_gp_max_dly', default=200.0, type=float, help="maximum delay in nanosec allowed for gaussian process fit")
a.add_argument('--bp_gp_nrestart', default=1, type=int, help='number of restarts for GP hyperparameter gradient descent.')
a.add_argument('--bp_gp_thin', default=2, type=int, help="thinning factor for freq bins in GP smooth fit")
# Misc
a.add_argument("--out_dir", default=None, type=str, help="output directory for calfits file. Default is working directory path")
a.add_argument("--overwrite", default=False, action="store_true", help="overwrite output calfits file if it exists")
a.add_argument("--multiply_gains", default=False, action="store_true", help="change gain_convention from divide to multiply.")
a.add_argument('--silence', default=False, action='store_true', help="silence output to stdout")

def echo(message, type=0, verbose=True):
    if verbose:
        if type == 0:
            print(message)
        elif type == 1:
            print('\n{}\n{}'.format(message, '-'*40))

def skynpz2calfits(fname, uv_file, dly_files=None, amp_files=None, bp_files=None, out_dir=None, phs_files=None, overwrite=False,
                   TTonly=True, plot_dlys=False, plot_phs=False, gain_convention='multiply', plot_bp=False, noBPphase=False,
                   noBPamp=False, bp_TTonly=False, bp_medfilt=False, medfilt_kernel=5, bp_amp_antavg=False, bp_flag_frac=0.3,
                   bp_broad_flags=False, medfilt_flag=False, bp_gp_smooth=False, bp_gp_max_dly=500.0, bp_gp_nrestart=1, bp_gp_thin=2,
                   plot_amp=False, gain_amp_antavg=False, verbose=True):
    """

    """
    # get out_dir
    if out_dir is None:
        out_dir = "./"

    # load UVData
    echo("...loading uv_file", verbose=verbose)
    uvd = UVData()
    uvd.read_miriad(uv_file)

    # get ants and antpos
    antpos, ants = uvd.get_ENU_antpos(center=True, pick_data_ants=True)
    ants = list(ants)

    # get freqs, times, jones
    freqs = uvd.freq_array.squeeze()
    times = uvd.time_array.reshape(uvd.Ntimes, uvd.Nbls)[:, 0]
    Ntimes = len(times)
    Nfreqs = len(freqs)
    Nants = len(ants)
    jones = uvd.polarization_array

    # construct blank gains and flags
    gains = np.ones((Nants, Nfreqs, Ntimes, 1), dtype=np.complex)
    flags = np.zeros((Nants, Nfreqs, Ntimes, 1), dtype=np.bool)
    flagged_ants = np.zeros(Nants, dtype=np.bool)

    # process delays if available
    if dly_files is not None:
        echo("...processing delays", verbose=verbose, type=1)
        delays = np.zeros_like(ants, dtype=np.float)
        delay_flags = np.zeros_like(ants, dtype=np.bool)
        for dly_file in dly_files:
            echo("...processing {}".format(dly_file))
            # get CASA delays and antennas
            dly_data = np.load(dly_file)
            dly_ants = dly_data['delay_ants']
            dlys = dly_data['delays']
            dly_flags = dly_data['delay_flags']
            dly_ants = dly_ants.tolist()
            dlys *= 1e-9
            # reorder antennas to be consistant w/ ants array
            dlys = np.array(map(lambda a: dlys[dly_ants.index(a)] if a in dly_ants else 0.0, ants))
            dly_flags = np.array(map(lambda a: dly_flags[dly_ants.index(a)] if a in dly_ants else True, ants))
            # keep only limited information
            if TTonly:
                echo("...keeping only TT component of delays", verbose=verbose)
                A = np.vstack([antpos[:, 0], antpos[:, 1]]).T
                fit = np.linalg.pinv(A.T.dot(A)).dot(A.T).dot(dlys)
                dlys = A.dot(fit)
            # add to delay array
            delays += dlys
            delay_flags += dly_flags
            flagged_ants += dly_flags

        # turn into complex gains
        dly_gains = np.exp(2j*np.pi*(freqs-freqs.min())*delays.reshape(-1, 1))[:, :, np.newaxis, np.newaxis]
        dly_gain_flags = delay_flags[:, np.newaxis, np.newaxis, np.newaxis]

        # multiply into gains
        gains *= dly_gains

        # add into flags
        flags += dly_gain_flags

    # process overall phase if available
    if phs_files is not None:
        echo("...processing gain phase", verbose=verbose, type=1)
        phases = np.zeros_like(ants, dtype=np.float)
        phase_flags = np.zeros_like(ants, dtype=np.bool)
        for phs_file in phs_files:
            echo("...processing {}".format(phs_file))
            # get phase antennas and phases
            phs_data = np.load(phs_file)
            phs_ants = phs_data['phase_ants']
            phs = phs_data['phases']
            phs_flags = phs_data['phase_flags']
            phs_ants = phs_ants.tolist()
            # reorder to match ants
            phs = np.array([phs[phs_ants.index(a)] if a in phs_ants else 0.0 for a in ants])
            phs_flags = np.array(map(lambda a: phs_flags[phs_ants.index(a)] if a in phs_ants else True, ants))
            # add to phases
            phases += phs
            phase_flags += phs_flags
            flagged_ants += phs_flags

        # construct gains
        phase_gains = np.exp(1j * phases)
        phase_gains = phase_gains[:, np.newaxis, np.newaxis, np.newaxis]
        phase_gain_flags = phase_flags[:, np.newaxis, np.newaxis, np.newaxis]

        # mult into gains
        gains *= phase_gains

        # add into flags
        flags += phase_gain_flags

    # process overall amplitude if available
    if amp_files is not None:
        echo("...processing gain amp", verbose=verbose, type=1)
        amplitudes = np.ones_like(ants, dtype=np.float)
        amplitude_flags = np.zeros_like(ants, dtype=np.bool)
        for amp_file in amp_files:
            echo("...processing {}".format(amp_file))
            # get amp antenna and amps
            amp_data = np.load(amp_file)
            amp_ants = amp_data['amp_ants']
            amps = amp_data['amps']
            amp_flags = amp_data['amp_flags']
            amp_ants = amp_ants.tolist()
            # reorder to match ants
            amps = np.array([amps[amp_ants.index(a)] if a in amp_ants else 1.0 for a in ants])
            amp_flags = np.array(map(lambda a: amp_flags[amp_ants.index(a)] if a in amp_ants else True, ants))
            # add to amplitudes
            amplitudes *= amps
            amplitude_flags += amp_flags
            flagged_ants += amp_flags

        # average across ants if desired
        if gain_amp_antavg:
            echo("...averaging antenna gain amplitudes", verbose=verbose)
            avg_amp = np.median(amplitudes[~amplitude_flags])
            amplitudes *= avg_amp / amplitudes

        # construct gains
        amplitude_gains = amplitudes
        amplitude_gains = amplitude_gains[:, np.newaxis, np.newaxis, np.newaxis]
        amplitude_flags = amplitude_flags[:, np.newaxis, np.newaxis, np.newaxis]

        # mult into gains
        gains *= amplitude_gains

        # add into flags
        flags += amplitude_flags

    # process bandpass if available
    if bp_files is not None:
        echo("...processing bandpass", verbose=verbose, type=1)
        for ii, bp_file in enumerate(bp_files):
            echo("...processing {}".format(bp_file))
            # get bandpass and form complex gains
            bp_data = np.load(bp_file)
            bp_freqs = bp_data['bp_freqs']
            bp_Nfreqs = len(bp_freqs)
            bandp_gains = bp_data['bp']
            bandp_flags = bp_data['bp_flags']
            bp_ants = bp_data['bp_ants'].tolist()
            # reorder to match ants
            bandp_gains = np.array([bandp_gains[:, bp_ants.index(a)].squeeze() if a in bp_ants else np.ones((bp_Nfreqs), dtype=np.complex) for a in ants])
            bandp_flags = np.array([bandp_flags[:, bp_ants.index(a)].squeeze() if a in bp_ants else np.ones((bp_Nfreqs), dtype=np.bool) for a in ants])
            # broadcast flags to all antennas at freq channels that satisfy bp_flag_frac
            flag_broadcast = (np.sum(bandp_flags, axis=0) / float(bandp_flags.shape[0])) > bp_flag_frac
            if bp_broad_flags:
                bandp_flags += np.repeat(flag_broadcast.reshape(1, -1).astype(np.bool), Nants, 0)
            # configure gains and flags shapes
            bandp_gains = bandp_gains[:, :, np.newaxis, np.newaxis]
            bandp_flags = bandp_flags[:, :, np.newaxis, np.newaxis]
            if ii == 0:
                bp_gains = bandp_gains
                bp_flags = bandp_flags
            else:
                bp_gains *= bandp_gains
                bp_flags += bandp_flags

        # median filter if desired
        if bp_medfilt or medfilt_flag:
            echo("...median filtering", verbose=verbose)
            bp_gains_medfilt = signal.medfilt(bp_gains.real, kernel_size=(1, medfilt_kernel, 1, 1)) + 1j*signal.medfilt(bp_gains.imag, kernel_size=(1, medfilt_kernel, 1, 1))

            if medfilt_flag:
                echo("...solving for BP flags w/ medfilt data")
                # get residual and MAD from unfiltered and filtered data
                residual = (np.abs(bp_gains) - np.abs(bp_gains_medfilt))
                residual[bp_flags] *= np.nan
                residual = residual.squeeze()
                resid_std = np.nanmedian(np.abs(residual - np.nanmedian(residual, axis=1)[:, np.newaxis]), axis=1) * 1.5
                # identify outliers as greater than 10-sigma
                bad = np.array([np.abs(residual[i]) > resid_std[i]*10 for i in range(residual.shape[0])])
                bp_flags += bad[:, :, np.newaxis, np.newaxis]

            if bp_medfilt:
                echo("...bandpass is the median filtered bandpass")
                bp_gains = bp_gains_medfilt

        # average amplitude across antenna if desired
        if bp_amp_antavg:
            echo("...averaging bandpass amplitude across antennas", verbose=verbose)
            amp_avg = np.nanmedian(np.abs(bp_gains), axis=0).reshape(1, -1, 1, 1)
            bp_gains *= amp_avg / np.abs(bp_gains)

        # smooth bandpass w/ gaussian process if desired
        if bp_gp_smooth:
            echo("...smoothing with gaussian process", verbose=verbose)
            freq_lambda = 1. / (bp_gp_max_dly*1e-3) # MHz
            kernel = 1**2 * gp.kernels.RBF(freq_lambda + 10, (freq_lambda, 200.0)) + gp.kernels.WhiteKernel(1e-4, (1e-8, 1e0))

            # configure data
            X = bp_freqs / 1e6
            bp_gains_real = []
            bp_gains_imag = []
            # iterate over antennas
            for i, a in enumerate(ants):
                if i % 10 == 0: echo("{}/{} ants".format(i, len(ants)), verbose=verbose)
                # skip flagged ants
                if np.min(bp_flags[i, :]):
                    bp_gains_real.append(np.ones_like(X.squeeze()))
                    bp_gains_imag.append(np.zeros_like(X.squeeze()))
                    continue
                GP = gp.GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=bp_gp_nrestart)
                xdata = X[~bp_flags[i].squeeze(), :][::bp_gp_thin]
                yreal = bp_gains[i].squeeze()[~bp_flags[i].squeeze()][::bp_gp_thin].real
                yimag = bp_gains[i].squeeze()[~bp_flags[i].squeeze()][::bp_gp_thin].imag
                ydata = np.vstack([yreal, yimag]).T
                ydata_med = np.median(ydata, axis=0)
                ydata -= ydata_med
                GP.fit(xdata, ydata)
                ypred = GP.predict(X) + ydata_med
                bp_gains_real.append(ypred[:, 0])
                bp_gains_imag.append(ypred[:, 1])
            # reconstruct bp gains
            bp_gains = (np.array(bp_gains_real) + 1j*np.array(bp_gains_imag))[:, :, np.newaxis, np.newaxis]

        # take only tip-tilt if desired
        if bp_TTonly:
            echo("...distilling bandpass to only tip-tilt phase", verbose=verbose)
            # get bandpass phase array
            bp_phs = np.angle(bp_gains).reshape(Nants, bp_Nfreqs)
            # form least squares estimate of phase slopes along X and Y
            A = np.vstack([antpos[:, 0], antpos[:, 1]]).T
            fit = np.linalg.pinv(A.T.dot(A)).dot(A.T).dot(bp_phs)
            # median filter
            fit = signal.medfilt(fit, kernel_size=(1, 11))
            # smooth across frequency via FFT
            window = signal.windows.gaussian(fit.shape[1], fit.shape[1]/50.0)
            fit_smooth = signal.fftconvolve(fit, window.reshape(1, -1), mode='same') / np.sum(window)
            # make prediction to get tip-tilt estimates
            bp_TT_phs = A.dot(fit_smooth).reshape(Nants, bp_Nfreqs, 1, 1)
            # update bandpass gains
            bp_gains *= np.exp(1j*bp_TT_phs - 1j*np.angle(bp_gains))

        # suppress amp and/or phase if desired
        if noBPamp:
            echo("...eliminating BP amplitudes", verbose=verbose)
            bp_gains /= np.abs(bp_gains)

        if noBPphase:
            echo("...eliminating BP phases", verbose=verbose)
            bp_gains /= np.exp(1j*np.angle(bp_gains))

        # mult into gains
        bp_freq_select = np.array([np.argmin(np.abs(freqs-x)) for x in bp_freqs])
        gains[:, bp_freq_select, :, :] *= bp_gains
        flags[:, bp_freq_select, :, :] += bp_flags
        bp_flagged_ants = np.min(bp_flags, axis=1).squeeze()
        flagged_ants += bp_flagged_ants

    # check filename
    if fname.split('.')[-1] != "calfits":
        fname += ".calfits"

    # make into calfits
    fname = os.path.join(out_dir, fname)
    echo("...writing to calfits {}".format(fname), verbose=verbose, type=1)
    make_calfits(fname, gains, freqs, times, jones, ants, flag_array=flags,
                 clobber=overwrite, gain_convention=gain_convention)

    # plot dlys
    if plot_dlys:
        fig, ax = plt.subplots(1, figsize=(8,6))
        ax.grid(True)
        dly_max = np.max(np.abs(delays*1e9))
        dly_min = -dly_max
        for i, a in enumerate(ants):
            if flagged_ants[i] == True:
                continue
            cax = ax.scatter(antpos[i, 0], antpos[i, 1], c=delays[i]*1e9, s=200, cmap='coolwarm', vmin=dly_min, vmax=dly_max)
            ax.text(antpos[i,0]+1, antpos[i,1]+2, str(a), fontsize=12)
        cbar = fig.colorbar(cax)
        cbar.set_label("delay [nanosec]", size=16)
        ax.set_xlabel("X [meters]", fontsize=14)
        ax.set_ylabel("Y [meters]", fontsize=14)
        ax.set_title("delay solutions for {}".format(os.path.basename(dly_files[0])), fontsize=10)
        fig.savefig(dly_files[0]+'.png', dpi=100, bbox_inches='tight', pad=0.05)
        plt.close()

    # plot phs
    if plot_phs:
        fig, ax = plt.subplots(1, figsize=(8,6))
        ax.grid(True)
        phs_max = np.pi
        phs_min = -np.pi
        for i, a in enumerate(ants):
            if flagged_ants[i] == True:
                continue
            cax = ax.scatter(antpos[i, 0], antpos[i, 1], c=phases[i], s=200, cmap='viridis', vmin=phs_min, vmax=phs_max)
            ax.text(antpos[i,0]+1, antpos[i,1]+2, str(a), fontsize=12) 
        cbar = fig.colorbar(cax)
        cbar.set_label("phase [radians]", size=16)
        ax.set_xlabel("X [meters]", fontsize=14)
        ax.set_ylabel("Y [meters]", fontsize=14)
        ax.set_title("phase solutions for {}".format(os.path.basename(phs_files[0])), fontsize=10)
        fig.savefig(phs_files[0]+'.png', dpi=100, bbox_inches='tight', pad=0.05)
        plt.close()

    # plot amp
    if plot_amp:
        fig, ax = plt.subplots(1, figsize=(8,6))
        ax.grid(True)
        amp_med = np.nanmedian(amplitudes[~amplitude_flags.squeeze()])
        amp_std = np.std(amplitudes[~amplitude_flags.squeeze()])
        amp_max = amp_med + amp_std * 2
        amp_min = amp_med - amp_std * 2
        for i, a in enumerate(ants):
            if flagged_ants[i] == True:
                continue
            cax = ax.scatter(antpos[i, 0], antpos[i, 1], c=amplitudes[i], s=200, cmap='rainbow', vmin=amp_min, vmax=amp_max)
            ax.text(antpos[i,0]+1, antpos[i,1]+2, str(a))
        cbar = fig.colorbar(cax)
        cbar.set_label("amplitude", size=16)
        ax.set_xlabel("X [meters]", fontsize=14)
        ax.set_ylabel("Y [meters]", fontsize=14)
        ax.set_title("amplitude solutions for {}".format(os.path.basename(amp_files[0])), fontsize=10)
        fig.savefig(amp_files[0]+'.png', dpi=100, bbox_inches='tight', pad=0.05)
        plt.close()

    # plot bandpass
    if plot_bp:
        fig, axes = plt.subplots(2, 1, figsize=(12,6))
        fig.subplots_adjust(hspace=0.3)
        # amplitude
        ax = axes[0]
        ax.grid(True)
        bp_gains[bp_flags] *= np.nan
        pls = []
        bp_ant_select = []
        ant_sort = np.argsort(ants)
        for i, a in enumerate(np.array(ants)[ant_sort]):
            if flagged_ants[ant_sort][i] == True:
                continue
            p, = ax.plot(bp_freqs / 1e6, np.abs(bp_gains).squeeze()[ants.index(a)], marker='.', ls='')
            pls.append(p)
        ax.set_xlabel("Frequency [MHz]", fontsize=12)
        ax.set_ylabel("Amplitude", fontsize=12)
        ax.set_title("bandpass for {}".format(bp_file), fontsize=10)
        # phase
        ax = axes[1]
        ax.grid(True)
        plot_ants = []
        for i, a in enumerate(np.array(ants)[ant_sort]):
            if flagged_ants[ant_sort][i] == True:
                continue
            plot_ants.append(a)
            ax.plot(bp_freqs / 1e6, np.angle(bp_gains).squeeze()[ants.index(a)], marker='.', ls='')
        ax.set_xlabel("Frequency [MHz]", fontsize=12)
        ax.set_ylabel("Phase [radians]", fontsize=12)
        lax = fig.add_axes([1.01, 0.1, 0.05, 0.8])
        lax.axis('off')
        lax.legend(pls, plot_ants, ncol=2)
        fig.savefig(bp_file+'.png', dpi=100, bbox_inches='tight', pad=0.05)
        plt.close()

if __name__ == "__main__":
    args = a.parse_args()

    gain_convention = 'divide'
    if args.multiply_gains:
        gain_convention = 'multiply'

    kwargs = copy.copy(args).__dict__
    kwargs.pop('fname')
    kwargs.pop('uv_file')
    kwargs.pop('multiply_gains')
    kwargs['verbose'] = args.silence == False
    kwargs.pop('silence')
    kwargs['gain_convention'] = gain_convention
    skynpz2calfits(args.fname, args.uv_file, **kwargs)

