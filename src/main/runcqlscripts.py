#!/usr/bin/env python3

import argparse
import subprocess
import os
import shutil
import pandas as pd
from utilities import *

parser = argparse.ArgumentParser(
    description='Run a folder containing cql scripts.'
)

parser.add_argument('--cql_scripts_dir', action='store', nargs='?', type=str, const='/Users/elliottmacneil/python/reti/src/FCE')
parser.add_argument('--db_dir', action='store', nargs='?', type=str, const='/Users/elliottmacneil/chess/pgn/hammratty2022.pgn')
parser.add_argument('--output_dir', action='store', nargs='?', type=str, const='/Users/elliottmacneil/python/reti/output')
parser.add_argument('--cql_bin_dir', action='store', nargs='?', type=str, const='/Users/elliottmacneil/chess/cql6/cql')

args = parser.parse_args()

cql_scripts_dir = args.cql_scripts_dir
cql_bin_dir = args.cql_bin_dir
db_dir = args.db_dir
output_dir = args.output_dir

print(cql_bin_dir)
print(db_dir)
print(output_dir)

if os.path.exists(output_dir) and os.path.isdir(output_dir):
    shutil.rmtree(output_dir)

os.mkdir(output_dir)

content = load_pgn(db_dir)
games = game_length_array(content)
num_games = len(games)

def run_cql_scripts(cql_scripts_dir):
    subgame_len = []
    all_scripts = []
    for file in os.listdir(cql_scripts_dir):
        file_dir = cql_scripts_dir+'/'+file
        file_noext = os.path.splitext(file)[0]
        dir_noext = os.path.join(output_dir,file_noext)
        pgn_file = dir_noext+'.pgn'
        cql_command = cql_bin_dir+' -i '+db_dir+' -o '+pgn_file+' -matchcount 2 100 '+file_dir
        subprocess.run(cql_command,shell=True)
        pgn = load_pgn(pgn_file)
        subgame_len.append(alt_num_games(pgn))
        all_scripts.append(file_noext)
    return subgame_len, all_scripts

def calculate_statistics(num_games, subgame_len):
    return [(idx*100)/num_games for idx in subgame_len]

subgame_len, all_scripts = run_cql_scripts(cql_scripts_dir)
stats = calculate_statistics(num_games, subgame_len)

df = pd.DataFrame({'ending-type': all_scripts,'len':subgame_len,'stats':stats})
df.to_csv('{}-games.csv'.format(db_dir))
