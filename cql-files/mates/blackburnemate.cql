// Searches for the blackburnemate checkmate pattern.



cql()
flipcolor{btm mate
B  attacks  k

square all x in _  attackedby  k
       (B  attacks  x) or (N  attacks  x)}

comment("blackburnemate")
