/*******
This illustrates how to convert the version
bristol1.cql using pieceids and directions instead of shifts
Note that this version is much faster than the version using shifts
*******/

cql(input hhdbvi.pgn )

 move from B
 piece Bishop in B
 line
         -->{ Q & diagonal 1 Bishop
              move from B}
         -->btm
         -->{ ray diagonal (Bishop Q)
              move from Q}
         -->Q & diagonal 1 Bishop

