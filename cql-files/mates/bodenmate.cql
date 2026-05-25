// Searches for the bodenmate checkmate pattern.



cql()
flipcolor{btm mate
B  attacks  k

square all x in _  attackedby  k
       B  attacks  x}

// Example pattern instance:
// cql() mate flipcolor shift flip {
//     kc8 rd8 pd7 Ba6 Bf4
// }

comment("bodenmate")
