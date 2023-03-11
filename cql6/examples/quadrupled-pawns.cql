/*********
Find games with quadrupled pawns. This is a direct translation of code
from the CQL version 3 using 'flip' and 'shift' .
**********/

cql(input hhdbvi.pgn)
 flipcolor
   shifthorizontal
     P[b2-7]>=4

