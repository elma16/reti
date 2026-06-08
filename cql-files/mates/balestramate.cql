// Searches for the balestramate checkmate pattern.

cql()
flipcolor{
mate
B  attacks  k
square all x in _  attackedby  k
(B  attacks  x) or (Q  attacks  x)}

