// doubleBishopMate - two bishops on parallel diagonals deliver mate

cql()
 flipcolor {btm mate
#(B  attacks  k) == 1
#B >= 2

square all x in _  attackedby  k
       B  attacks  x}

comment("doubleBishopMate")
