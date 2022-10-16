#!/usr/bin/env python3

import argparse
import subprocess
import os
import shutil
import pandas as pd
from utilities import *


# TODO add this to a text file?
#
parser = argparse.ArgumentParser(
    description='Make the table from Fundamental Chess Endings'
)

parser.add_argument('cql_dir', action='store', type=str, default='./')
parser.add_argument('db_dir', action='store', type=str, default='./')
parser.add_argument('output_dir', action='store', type=str, default='./')

args = parser.parse_args()

cql_dir = args.cql_dir
db_dir = args.db_dir
output_dir = args.output_dir

if os.path.exists(output_dir) and os.path.isdir(output_dir):
    shutil.rmtree(output_dir)

os.mkdir(output_dir)

content = load_pgn(db_dir)
games = game_length_array(content)
num_games = len(games)


def fce_cql():
    subgame_len = []
    all_scripts = []
    path = '/Users/elliottmacneil/chess/reti/src/FCE'
    for file in os.listdir(path):
        file_dir = path+'/'+file
        file_noext = os.path.splitext(file)[0]
        dir_noext = os.path.join(output_dir,file_noext)
        pgn_file = dir_noext+'.pgn'
        cql_command = cql_dir+' -i '+db_dir+' -o '+pgn_file+' -matchcount 2 100 '+file_dir
        subprocess.run(cql_command,shell=True)
        pgn = load_pgn(pgn_file)
        game2 = alt_num_games(pgn)
        subgame_len.append(game2)
        all_scripts.append(file_noext)
    return subgame_len, all_scripts

def calculate_statistics():
    stats = []
    for idx in subgame_len:
        stats.append((idx*100)/num_games)
    return stats

subgame_len, all_scripts = fce_cql()
stats = calculate_statistics()

df = pd.DataFrame({'ending-type': all_scripts,'len':subgame_len,'stats':stats})
df.to_csv('games.csv')
