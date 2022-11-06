#!/usr/bin/env python3

import chess
import chess.engine
import chess.pgn
import re
import numpy as np
from stockfish import Stockfish
import sys
import matplotlib.pyplot as plt
from utilities import *

'''
thoughts:
 - given the person's name, work out their score as the length of the game gets longer

'''

stockfish = Stockfish(path='/opt/homebrew/Cellar/stockfish/15/bin/stockfish',
                      depth=18,
                      parameters={"Threads": 1, "Hash":16})

pgn = open(sys.argv[1])
content = load_pgn(sys.argv[1])
games = game_length_array(content)

print('mean length', np.mean(games))
print('number of games', len(games))
print('max game length', np.max(games))
print('min game length', np.min(games))

plt.hist(games,bins=len(set(games)))
plt.show()

num_games = len(games)
engine = chess.engine.SimpleEngine.popen_uci('/opt/homebrew/Cellar/stockfish/15/bin/stockfish')

move_evals = np.zeros((num_games,num_games))
depth = np.zeros((num_games,num_games))
game_num = -1
for game in range(num_games):
  first_game = chess.pgn.read_game(pgn)
  game_num += 1
  print(game_num)
  board = first_game.board()
  move_num = -1
  for move in first_game.mainline_moves():
    board.push(move)
    move_num += 1
    info = engine.analyse(board, chess.engine.Limit(time=0.01))
    eval = str(re.findall(r'\(.{1,5}\)',str(info['score']))[0])[1:-1:1]
    if eval[0] == 'C':
      eval = eval[3::]
    eval = int(eval)/100
    colour = re.findall(r'WHITE|BLACK',str(info['score']))[0]
    if colour == 'BLACK':
      eval *= -1
    move_evals[game_num,move_num] = eval
    depth[game_num,move_num] = info['depth']
  print(board)

print(move_evals)
engine.quit()
