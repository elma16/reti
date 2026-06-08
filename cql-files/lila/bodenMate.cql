// bodenMate - two bishops on criss-crossing diagonals deliver mate

cql()
 flipcolor {btm mate
B  attacks  k
#(B  attacks  k) == 2

square all x in _  attackedby  k
       B  attacks  x}

