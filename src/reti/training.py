import webbrowser
import chess
import numpy as np

class EndgameTraining(Training):
    def __init__(self):
        self.white = None
        self.black = None
    def random_generate(self):
        '''
        Generate a training game by randomly making a position
        '''
        board = chess.Board()
        pieces = white + black
        pieces = [chess.Piece.from_symbol(x) for x in pieces]

        # clear board
        for square in chess.SQUARES:
            board.remove_piece_at(square)
        
        while not board.is_valid() and board.is_empty():
        squares = np.random.choice([0,63], len(pieces), replace=False)

        for idx in range(len(pieces)):
            board.set_piece_at(squares[idx], pieces[idx])
        if board.is_valid():
            return board
        else:
            return None
            
        fen = '////// w KQkq - 0 1'
        webbrowser.open('https://lichess.org/editor/'+fen.replace(' ','_'))
        pass
    def game_generate(self):
        '''
        Generate a training game by cql
        '''
        pass
    def logical_generate(self):
        '''
        Generate a training game by randomly making a position from logical rules
        '''
        pass
    def tablebase_generate(self):
        '''
        Generate a training game by randomly making a position from tablebase
        '''
        pass

