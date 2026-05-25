// discoveredAttack - a piece moves off a line revealing an attack by another piece

cql()
 flipcolor {(A & ~(move to . previous))  attacks  k}

comment("discoveredAttack")
