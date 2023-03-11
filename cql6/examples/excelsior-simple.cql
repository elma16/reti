/********
This file finds games at least one White excelsior.
See excelsior-multiple.cql for games with multiple excelsiors of either color
It illustrates that the ID of a piece does not change after promotion
********/

cql(input hhdbvi.pgn )

initial
piece Pawn in Pa-h2
  find move from Pawn promote A 
  
