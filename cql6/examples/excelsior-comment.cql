/**************
This file is based on the file excelsior-multiple.cql . 
It modifies that file by using the comment filter
to output the actual squares on which the excelsior was found
**********/

cql(input hhdbvi.pgn)
initial
x = piece Excelsior in Pa-h2 | pa-h7
      find
        move promote A from Excelsior

// the variable x now holds the squares where an Excelsior pawn is starting out

sort "Number of excelsiors"
   x
   >1
comment ("Excelsiors at: " x)
