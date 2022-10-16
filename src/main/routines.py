#!/usr/bin/env python3

import sys
import re

def get_games(path):
    '''
    Given the path to a pgn, output a string of all the games.
    '''
    with open(path) as file:
        content = file.read()
    return content

def game_length_array(content):
    '''
    Given a string of the pgn, output an array where each entry is the length of the game
    '''
    # does this regex work? ^\d{1,3}.*0-1$
    game_array = re.findall(r'\d{1,3}\.\s',content)
    game_array = [int(x[:-2]) for x in game_array]
    begin_indices = [i for i, x in enumerate(game_array) if x == 1]
    end_indices = [x-1 for x in begin_indices]
    end_indices = end_indices[1::]
    end_move = [game_array[x] for x in end_indices]
    end_move.append(game_array[-1])
    return end_move

def average_game_length(content):
    return np.mean(game_length_array(content))

def number_of_games(content):
    return len(game_length_array(content))

def max_game_length(content):
    return np.max(game_length_array(content))

def min_game_length(content):
    return np.min(game_length_array(content))
