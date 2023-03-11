/*********
This the platzwechseln theme: two (white) knights interchange places
*********/

cql( input hhdbvi.pgn )
 Start=currentposition
 piece Knight1 in N
  piece Knight2 in N & ~Knight1
   find Knight1 == Start:Knight2
        and  Knight2 == Start:Knight1
         
