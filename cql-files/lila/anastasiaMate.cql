// anastasiaMate - king on a/h file mated by rook/queen with knight support

cql()
 flipcolor {btm mate
R  attacks  k
_  attackedby  k == 4

square all x in _  attackedby  k
       (R  attacks  x) or (N  attacks  x)}

comment("anastasiaMate")
