/*seems exactly the same as greco's mate*/

cql()
flipcolor{btm mate
Q  attacks  k

square all x in _  attackedby  k
       (B  attacks  x) or (Q  attacks  x)}

//cql() mate flipcolor shift flip {
//    Bf7 Qg8 kh7
//}

comment("maxlangemate")
