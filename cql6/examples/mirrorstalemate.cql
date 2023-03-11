/* Mirror stalemate: one side is stalemated surrounded by empty squares */

cql(input hhdbvi.pgn)
 flipcolor{
   btm
   stalemate
   _ attackedby k == 8
   }
   