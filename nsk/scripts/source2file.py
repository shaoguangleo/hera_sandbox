#!/usr/bin/env python2.7
"""
source2file.py
=============

Given a calibrator source,
output the files that contain
when it is closest to zenith

"""
import os
import numpy as np
import argparse
from astropy.time import Time
from RA2LST import RA2LST
import JD2LST
from pyuvdata import UVData
import sys

ap = argparse.ArgumentParser(description='')

ap.add_argument("--ra", type=float, help="RA of the source in degrees", required=True)
ap.add_argument("--lon", default=21.428305555, type=float, help="longitude of observer in degrees East")
ap.add_argument("--duration", default=2.0, type=float, help="duration in minutes of calibrator integration")
ap.add_argument("--offset", default=0.0, type=float, help="offset from closest approach in minutes")
ap.add_argument("--start_jd", default=None, type=int, help="starting JD of interest")
ap.add_argument("--jd_files", default=None, type=str, nargs='*',  help="glob-parsable search of files to isolate calibrator in.")
ap.add_argument("--get_filetimes", default=False, action='store_true', help="open source files and get more accurate duration timerange")

if __name__ == "__main__":
    # parse arge
    a = ap.parse_args()

    # get LST of the source
    lst = RA2LST(a.ra, a.lon)
    # offset
    lst += args.offset / 60.

    print("-"*60)
    print("source LST (offset by {} minutes) = {} Hours".format(args.offset, lst))
    print("-"*60)

    if a.start_jd is not None:
        # get JD when source is at zenith
        jd = JD2LST.LST2JD(lst, a.start_jd, a.lon)
        print("JD closest to zenith (offset by {} minutes): {}".format(args.offset, jd))
        print("-"*60)

        # print out UTC time
        jd_duration = a.duration / (60. * 24 + 4.0)
        time1 = Time(jd - jd_duration/2, format='jd').to_datetime()
        time2 = Time(jd + jd_duration/2, format='jd').to_datetime()
        time3 = Time(jd, format='jd').to_datetime()
        print('UTC time range of {} minutes is:\n' \
              '"{:04d}/{:02d}/{:02d}/{:02d}:{:02d}:{:02d}~{:04d}/{:02d}/{:02d}/{:02d}:{:02d}:{:02d}", ' \
              'centered on {:04d}/{:02d}/{:02d}/{:02d}:{:02d}:{:02d}'.format(a.duration,
                                                        time1.year, time1.month, time1.day,
                                                        time1.hour, time1.minute, time1.second,
                                                        time2.year, time2.month, time2.day,
                                                        time2.hour, time2.minute, time2.second,
                                                        time3.year, time3.month, time3.day,
                                                        time3.hour, time3.minute, time3.second))
        print("-"*60)

    if a.jd_files is not None:
        if a.start_jd is None:
            raise AttributeError("need start_jd to search files")
        # get files
        files = a.jd_files
        if len(files) == 0:
            raise AttributeError("length of jd_files is zero")
        # keep files with start_JD in them
        file_jds = []
        for i, f in enumerate(files):
            if str(a.start_jd) not in f:
                files.remove(f)
            else:
                fjd = os.path.basename(f).split('.')
                findex = fjd.index(str(a.start_jd))
                file_jds.append(float('.'.join(fjd[findex:findex+2])))
        files = np.array(files)[np.argsort(file_jds)]
        file_jds = np.array(file_jds)[np.argsort(file_jds)]

        # get file with closest jd1 that doesn't exceed it
        jd1 = jd - jd_duration / 2
        jd2 = jd + jd_duration / 2

        jd_diff = file_jds - jd1
        jd_before = jd_diff[jd_diff < 0]
        if len(jd_before) == 0:
            start_index = np.argmin(np.abs(jd_diff))
        else:
            start_index = np.argmax(jd_before) 

        # get file closest to jd2 that doesn't exceed it
        jd_diff = file_jds - jd2
        jd_before = jd_diff[jd_diff < 0]
        if len(jd_before) == 0:
            end_index = np.argmin(np.abs(jd_diff))
        else:
            end_index = np.argmax(jd_before)  

        print("file(s) closest to source (offset by {} minutes) over {} min duration:\n {}".format(args.offset, a.duration, files[start_index:end_index+1]))
        print("-"*60)

        if a.get_filetimes:
            # Get UTC timerange of source in files
            source_files = files[start_index:end_index+1]
            uvd = UVData()
            for i, sf in enumerate(source_files):
                if i == 0:
                    uvd.read_miriad(sf)
                else:
                    uv = UVData()
                    uv.read_miriad(sf)
                    uvd += uv
            file_jds = np.unique(uvd.time_array)
            file_delta_jd = np.median(np.diff(file_jds))
            file_delta_min =  file_delta_jd * (60. * 24 + 4.0)
            num_file_times = int(np.ceil(a.duration / file_delta_min))
            file_jd_indices = np.argsort(np.abs(file_jds - jd))[:num_file_times]
            file_jd1 = file_jds[file_jd_indices].min()
            file_jd2 = file_jds[file_jd_indices].max()

            time1 = Time(file_jd1, format='jd').to_datetime()
            time2 = Time(file_jd2, format='jd').to_datetime()
            print('UTC time range of source in files above over {} minutes is:\n' \
                  '"{:04d}/{:02d}/{:02d}/{:02d}:{:02d}:{:02d}~{:04d}/{:02d}/{:02d}/{:02d}:{:02d}:{:02d}", '.format(a.duration,
                                                            time1.year, time1.month, time1.day,
                                                            time1.hour, time1.minute, time1.second,
                                                            time2.year, time2.month, time2.day,
                                                            time2.hour, time2.minute, time2.second))
            print("-"*60)








