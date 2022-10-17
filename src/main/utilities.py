#!/usr/bin/env python3

import re

def game_length_array(content):
  game_array = re.findall(r'\d{1,3}\.\s',content)
  game_array = [int(x[:-2]) for x in game_array]
  begin_indices = [i for i, x in enumerate(game_array) if x == 1]
  end_indices = [x-1 for x in begin_indices]
  end_indices = end_indices[1::]
  end_move = [game_array[x] for x in end_indices]
  if len(game_array) > 0:
      end_move.append(game_array[-1])
  else:
      return []
  return end_move

def alt_num_games(content):
    results = re.findall(r'Result\s"',content)
    return len(results)

def load_pgn(path):
    enc = 'iso-8859-15'
    with open(path, 'r', encoding=enc) as file:
        content = file.read()
    return content
