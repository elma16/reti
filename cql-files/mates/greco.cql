// Searches for the greco checkmate pattern.

cql()
flipcolor{btm mate
Q  attacks  k

square all x in _  attackedby  k
       (B  attacks  x) or (Q  attacks  x)}


// if you wanted to sort by which has more pieces
//sort power a

comment("greco")
