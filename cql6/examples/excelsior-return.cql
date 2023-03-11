/*****
This file finds games with an excelsior where the promoted piece
returns to its original square
********/

cql(input hhdbvi.pgn )

initial
Start=currentposition
 piece Excelsior in Pa-h2 | pa-h7
   find move from Excelsior
              to Start:Excelsior
   
  
