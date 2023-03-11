/********
Platzwechseln theme.
A white and black knight switch places.
They are separated by at least 3 squares both horizontally and vertically
*********/

cql(input hhdbvi.pgn )
Start=currentposition
piece Knight1 in N
 piece Knight2 in n {
   abs (rank Knight1 - rank Knight2) >=3 
   abs (file Knight1 - file Knight2) >=3
   find Knight1 == Start:Knight2
        and  Knight2 == Start:Knight1
   } //piece Knight 2...















