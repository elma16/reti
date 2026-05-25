// arabian mate

// the knight and the rook team up to trap the opposing king on a corner of the board. The rook sits on a square adjacent to the king both to prevent escape along the diagonal
// and to deliver checkmate while the knight sits two squares away diagonally from the king to prevent escape on the square next to the king and to protect the rook.

cql()
flipcolor{btm mate
R  attacks  k
k  attacks  R
N  attacks  R
_  attackedby  k == 2}


//cql() mate flipcolor shift flip {
//    Nf6 Rh7 kh8
//}

comment("arabianmate")
