/********
Games with positions in which at least 3 non-pawn pieces by one side are
immured, sorted by the number of such
pieces.

An immured piece is a piece that is not pinned and has no legal moves
**********/

cql(input hhdbvi.pgn)
⬓{wtm not check
 3≤sort "Number of immured pieces"
     I∊♖♘♗♕∩~pin
      not legal I――
}    
     
 
