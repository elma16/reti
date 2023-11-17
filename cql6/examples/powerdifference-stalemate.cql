/***********
Stalemates where difference in power between the stalemated side
and the stalemating side is
at least 10, sorted by that difference
**********/

cql(input hhdbvi.pgn)

 ⬓{ wtm
   stalemate
   sort "difference in power between stalemated and stalemating sides"
     power△ - power▲ ≥ 10
 }




