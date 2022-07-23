#!/usr/bin/env python3

import argparse
import subprocess
import os

parse = argparse.ArgumentParser(
    description='Make the table from Fundamental Chess Endings'
)

parser.add_argument('cql_dir', action='store', type=str, default='./')
parser.add_argument('db_dir', action='store', type=str, default='./')
parser.add_argument('output_dir', action='store', type=str, default='./')

args = parser.parse_args()

cql_dir = args.cql_dir
db_dir = args.db_dir
output_dir = args.db_dir

subprocess('rm -rf '+output_dir, shell=True)

subprocess('mkdir '+output_dir, shell=True)

total_games = subprocess('grep -o '+'Result'+db_dir+'| wc -l', shell=True)

directory = os.fsencode('src/FCE')
for file in os.listdir(directory):
    file_noext = os.path.splitext(file)[0]
    dir_noext = os.path.join(output_dir,file_noext)
    pgn_file = dir_noext+'.pgn'
    gamenum_dir = os.path.join(output_dir,gamenum.txt)
    stats_dir = os.path.join(output_dir,stats.txt)
    subprocess(cql_dir+'-i'+db_dir+'-o'+pgn_file+' -matchcount 2 100'+file,shell=True)
    subprocess('grep -o'+'Result'+pgn_file+'|wc -l >>'+gamenum, shell=True)

def calculate_statistics():
    subprocess('awk -v c='+total_games+'{for (i = 1; i <= NF; ++i) $i /= (c / 100); print }'+'OFS=\t'+gamenum_dir+'>'+stats_dir, shell=True)
