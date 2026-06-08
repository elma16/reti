// Searches for the morphymate checkmate pattern.




cql()
flipcolor{btm mate
B  attacks  k
_  attackedby  k == 2

square all x in _  attackedby  k
       (B  attacks  x) or (R  attacks  x)}

//cql() mate flipcolor shift flip {
//    Bf6 Rg1 kh8 
//}

