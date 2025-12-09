#!/usr/bin/env python3
# TMC drivers registers calibration tool (plotter)
#
# Copyright (C) 2024  Alexander Fedorov <altzbox@gmail.com>
# Copyright (C) 2024  Maksim Bolgov <maksim8024@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import glob
import os, sys, csv
import numpy as np
from tqdm import tqdm
import plotly.graph_objects as go
import plotly.io as pio
from datetime import datetime

#################################################################################################################
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_RESULTS_FOLDER = os.path.expanduser(
    '~/printer_data/config/adxl_results/chopper_magnitude'
)
DEFAULT_DATA_FOLDER = os.path.join(SCRIPT_DIR, 'csv')
#################################################################################################################

FCLK = 12 # MHz
CUTOFF_RANGE = 5

def cleaner(data_folder):
    for csv_path in glob.glob(os.path.join(data_folder, '*.csv')):
        try:
            os.remove(csv_path)
        except OSError as exc:
            print(f'Could not remove {csv_path}: {exc}')
    sys.exit(0)

def check_export_path(path):
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            print(f'Error generate path {path}: {e}')

def parse_arguments():
    args = sys.argv[1:]
    parsed_args = {}
    for arg in args:
        name, value = arg.split('=', 1)
        parsed_args[name] = int(value) if value.isdigit() else value
    return parsed_args


def resolve_path(arg_value, env_var, default_value):
    candidate = arg_value or os.environ.get(env_var) or default_value
    expanded = os.path.abspath(os.path.expanduser(candidate))
    return expanded


def get_data_folder(path):
    if not os.path.isdir(path):
        raise FileNotFoundError(
            f'CSV data folder not found: {path}. Set CHOPPER_DATA_FOLDER/data_folder to your CSV directory'
        )
    return path

def calc_static_magnitude(file):
    data = np.array([
        [float(row["accel_x"]),
         float(row["accel_y"]),
         float(row["accel_z"])] for row in csv.DictReader(file)])
    return np.mean(data, axis=0)

def calc_magnitude(file, static_data):
    data = np.array([
        [float(row["accel_x"]),
         float(row["accel_y"]),
         float(row["accel_z"])] for row in csv.DictReader(file)]) - static_data
    trim_size = len(data) // CUTOFF_RANGE
    data = data[trim_size:-trim_size]
    md_magnitude = np.median(np.linalg.norm(data, axis=1))
    return md_magnitude

def main():
    print('Magnitude graphs generation...')
    args = parse_arguments()
    data_folder = get_data_folder(resolve_path(args.get('data_folder'), 'CHOPPER_DATA_FOLDER', DEFAULT_DATA_FOLDER))
    results_folder = resolve_path(args.get('results_folder'), 'CHOPPER_RESULTS_FOLDER', DEFAULT_RESULTS_FOLDER)
    check_export_path(results_folder)
    print(f'Using data folder: {data_folder}')
    print(f'Exporting plots to: {results_folder}')
    driver = args.get('driver')
    iterations = args.get('iterations')
    sense_resistor = round(float(args.get('sense_resistor')), 3)
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Calc static magnitude
    static_name = next((name for name in os.listdir(data_folder) if name.endswith('stand_still.csv')), None)
    if not static_name:
        raise FileNotFoundError(f'Could not find stand_still.csv in {data_folder}. Did you copy the measurement CSV files?')
    with open(os.path.join(data_folder, static_name), 'r') as file:
        static_data = calc_static_magnitude(file)
        accel_chip = static_name.split('-')[0]
    # Calc magnitudes on registers
    samples = {}
    datapoint = []
    empty_error = 0
    data_files = sorted(os.listdir(data_folder), key=lambda x: os.
                        path.getmtime(os.path.join(data_folder, x)), reverse=True)
    for name in data_files:
        if name.endswith('__.csv'):
            with open(os.path.join(data_folder, name), 'r') as file:
                curr, tbl, toff, hstrt, hend, tpfd, speed, freq, iter = name.split('__')[1].split('_')
                out_name = (f'current={curr}_tbl={tbl}_toff={toff}_hstrt={hstrt}_hend={hend}'
                            f'_tpfd={tpfd}_speed={float(speed)/100:.2f}_freq={float(freq)/1000:.2f}kHz')
                try:
                    md_magnitude = calc_magnitude(file, static_data)
                    datapoint.append(md_magnitude)
                    if int(iter) == iterations:
                        samples[out_name] = np.mean(datapoint, axis=0)
                        datapoint.clear()
                except:
                    datapoint.clear()
                    empty_error += 1
                    samples[out_name] = 0

    # Graphs generation
    colors = ['', '#2F4F4F', '#12B57F', '#9DB512', '#DF8816', '#1297B5', '#5912B5', '#B51284', '#127D0C']
    params = [reversed(list(samples.items())), sorted(samples.items(), key=lambda x: x[1])]
    names = ['', 'sorted_']
    for param, name in zip(params, names):
        fig = go.Figure()
        for entry in param:
            toff = int(entry[0].split('_')[2].split('=')[1])
            color = colors[toff if toff <= 8 else toff - 8]
            fig.add_trace(go.Bar(x=[entry[1]], y=[entry[0]], marker_color=color, orientation='h', showlegend=False))
        fig.update_layout(title='Median Magnitude vs Parameters', xaxis_title='Median Magnitude',
                          yaxis_title='Parameters', coloraxis_showscale=True)
        plot_html_path = os.path.join(results_folder, f'{name}interactive_plot_{accel_chip}_tmc{driver}_{sense_resistor}_{now}.html')
        pio.write_html(fig, plot_html_path, auto_open=False)
        speed1 = params[1][0][0].split('_')[6].split('=')[1]
        speed2 = params[1][1][0].split('_')[6].split('=')[1]
        if speed1 != speed2:
            break

    # Export Info
    try:
        print(f'Access to interactive plot at: {"/".join(plot_html_path.split("/")[:-1] + [plot_html_path.split(names[1])[1]])}')
    except IndexError:
        print(f'Access to interactive plot at: {plot_html_path}')
    if empty_error:
        print(f'Warning!!! Empty data cells detected ({empty_error}), make sure you dont run out of memory')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'cleaner':
        cleaner(resolve_path(None, 'CHOPPER_DATA_FOLDER', DEFAULT_DATA_FOLDER))
    main()
