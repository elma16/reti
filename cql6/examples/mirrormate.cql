/* Mirror mate: one side is mated surrounded by empty squares */

cql(input hhdbvi.pgn)
 flipcolor{
   btm
   mate
   _ attackedby k == 8
   }
   