// arabianMate - king in corner mated by rook and knight

cql()
 flipcolor {mate
R  attacks  k
k  attacks  R
N  attacks  R
_  attackedby  k == 2}

