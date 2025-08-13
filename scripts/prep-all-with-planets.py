#! /usr/bin/env python
#######################################################################
# The script to prepare ALL of the "orbitals" data e.g. Sun, satellites
#######################################################################
# %reload_ext autoreload
# %autoreload 2

import argparse
import os
import sys
import time
from sys import exit

import h5py
import numpy as np
import yaml

# os.environ['ASTROPY_DOWNLOAD_CACHE_LOCK_ATTEMPTS'] = '1'
# os.environ['ASTROPY_PARALLEL_DOWNLOAD'] = 'False'


# --- Environment ------------------------------------------------------------
def add_optional_path(env_var: str) -> None:
    path = os.getenv(env_var)
    if path:
        print(f"The {env_var} is defined in the environment: {path}, will be added to sys.path")
        sys.path.append(path)

add_optional_path("LUSEEPY_PATH")
add_optional_path("LUSEEOPSIM_PATH")

# for path_part in sys.path:
#     if path_part != '': print(f'''{path_part}''')


def compute_satellite_track(observation, sat_config):
    semi_major_km = sat_config['semi_major_km']
    eccentricity = sat_config['eccentricity']
    inclination_deg = sat_config['inclination_deg']
    raan_deg = sat_config['raan_deg']
    argument_of_pericenter_deg = sat_config['argument_of_pericenter_deg']
    aposelene_ref_time = Time(sat_config['aposelene_ref_time'])

    satellite = lusee.Satellite(
        semi_major_km, eccentricity, inclination_deg,
        raan_deg, argument_of_pericenter_deg, aposelene_ref_time
    )
    return lusee.ObservedSatellite(observation, satellite)


def inspect_file():
    pass


def produce_data(conf, verbose: bool = False):
    if verbose:
        print("*** Top-level configuration keys ***")
        print(*conf.keys())

    prd = conf['period']
    t_start, t_end, deltaT = (prd['start'], prd['end'], prd['deltaT'])

    if verbose:
        print(f"Time range: {t_start} to {t_end}, time step: {deltaT}")

    # Lander location
    loc = conf['location']
    lat = loc['latitude']
    lon = loc['longitude']
    hgt = loc['height']

    print(f"Latitude: {lat}, longitude: {lon}")

    observation = lusee.Observation((t_start, t_end), lat, lon, hgt, deltaT)

    start = time.time()

    bodies_data = {body: track_from_observation(observation, body) for body in conf['bodies']}

    print(f"ELAPSED time (bodies_data): {time.time() - start} seconds")
    start = time.time()

    sat_data = {sat_name: compute_satellite_track(observation, conf["satellites"][sat_name]) for sat_name in
                ["lpf", "bge"]}

    print(f"ELAPSED time (sat_data): {time.time() - start} seconds")

    return bodies_data, sat_data


def write_to_file(outputfile: str, conf, bodies_data, sat_data, verbose: bool = False):
    start = time.time()
    if outputfile == '':  # print useful info and exit
        if verbose:
            print(f'No output file name detected, will exit now.')
        exit(0)

    f = h5py.File(outputfile, 'w')

    grp_meta = f.create_group('meta')
    dt = h5py.string_dtype(encoding='utf-8')
    ds_meta = grp_meta.create_dataset('configuration', (1,), dtype=dt)
    ds_meta[0,] = yaml.dump(conf)

    (times_sun, alt_sun, az_sun) = bodies_data['sun']
    mjd_sun = [t.mjd for t in times_sun]

    grp_data = f.create_group('orbitals')
    grp_data.create_dataset("mjd", data=mjd_sun)

    for body, body_data in bodies_data.items():
        b_group = grp_data.create_group(body)
        b_group.create_dataset("alt", data=body_data[2])
        b_group.create_dataset("az", data=body_data[1])

    for sat_name, obs_satellite in sat_data.items():
        s_group = grp_data.create_group(sat_name)
        s_group.create_dataset("alt", data=obs_satellite.alt)
        s_group.create_dataset("az", data=obs_satellite.az)
        s_group.create_dataset("dist_km", data=obs_satellite.dist_km())

    f.close()
    end = time.time()
    print(f"ELAPSED writing file: {end - start} seconds")


def read_config(conffile, verbose: bool = False):
    if conffile == '':
        print('Missing configuration, exiting...')
        exit(-2)

    try:
        conf_f = open(conffile, 'r')
        conf = yaml.safe_load(conf_f)  # ingest the configuration data
    except:
        print('Error opening and reading the configuration file:', conffile)
        exit(-2)

    if verbose:
        print("*** Top-level configuration keys ***")
        print(*conf.keys())

    return conf


def main():
    # lusee/opsim
    # NB: import must happen in the function, not on the module level
    # to run on MacOS

    # ----------------------------------------------------------------------------------
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose", action='store_true', help="Verbose mode")
    parser.add_argument("-c", "--conffile", type=str, help="The input - a YAML file containing configuration",
                        default='')
    parser.add_argument("-o", "--outputfile", type=str, help="The output", default='')
    parser.add_argument("-i", "--inspectfile", type=str, help="File to inspect (overrides other options)", default='')
    # ----------------------------------------------------------------------------------
    args = parser.parse_args()

    verbose = args.verbose
    conffile = args.conffile
    outputfile = args.outputfile
    inspectfile = args.inspectfile

    # ---
    if verbose:
        print("*** Verbose mode ***")
        if inspectfile == '':
            print(f'''*** Configuration file (YAML): "{conffile}" ***''')
            print(f'''*** Output file (HDF5): "{outputfile}" ***''')
        else:
            print(f'''*** File to inspect (will exit on completion): "{inspectfile}" ***''')

    # ----------------------------------------------------------------------------------
    # -- INSPECT EXISTING DATA
    if inspectfile != '':  # inspect and exit
        f = h5py.File(inspectfile, "r")
        ds_meta = f["/meta/configuration"]
        conf = yaml.safe_load(ds_meta[0,])
        check = yaml.dump(conf)
        print(check)

        ds_data = f["/data/orbitals"]
        data_array = np.array(ds_data[:])
        print(f'''Shape of the data payload: {data_array.shape}''')

        print('First 10 rows')
        print(data_array[:10])

        exit(0)

    conf = read_config(conffile, verbose)

    if verbose:
        # Lander location
        loc = conf['location']
        lat = loc['latitude']
        lon = loc['longitude']
        print(f"Latitude: {lat}, longitude: {lon}")

    bodies_data, sat_data = produce_data(conf, verbose)

    write_to_file(outputfile, conf, bodies_data, sat_data, verbose)


if __name__ == '__main__':
    from nav.coordinates import track_from_observation
    import lusee
    from lunarsky.time import Time

    main()
