/******
Queen - Bishop bristols. This is a direct translation of CQL version 3 file
bristol.cql

******/

cql(input hhdbvi.pgn)
line
  -->shift {move from Bd4
         Q[c3,e3,e5,c5]}
  -->.
  -->{move from Q
      ray diagonal (B Q)}
  -->shift {Bd4 Q[c3,e4,e5,c5]}


