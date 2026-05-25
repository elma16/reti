// Searches for the rookmate checkmate pattern.




cql()
flipcolor{btm mate
R  attacks  k
_  attackedby  k == 5

square all x in _  attackedby  k
       (B  attacks  x) or (K  attacks  x)}

comment("rookmate")
