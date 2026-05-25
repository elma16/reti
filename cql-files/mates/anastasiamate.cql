// anastasia's mate 

// a knight and rook team up to trap the opposing king between the side of the board on one side and a friendly piece on the other.

cql()
flipcolor{btm mate
R  attacks  k
_  attackedby  k == 4


square all x in _  attackedby  k
       (R  attacks  x) or (N  attacks  x)}


//cql() mate flipcolor shift flip {
//   Ne7 pg7 Rh5 kh7
//}

comment("anastasiamate")
