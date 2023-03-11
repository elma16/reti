/************
delayed white clearance:
 (1) White moves a piece, the "vacater" to an empty square.
 (2) Black immediately captures that piece
 (3) Later another white piece, the exploiter, crosses the square
     that the vacater had vacated by moving. But the exploiter
     did not move between (1) and (3).
The output is sorted by the length of the delay between (2) and (3)
Note that the reported length by sort is actually 4 positions LONGER
than the delay between (2) and (3), due to the other positions in the
sequence.
***********/

cql(input hhdbvi.pgn)
wtm
Start=currentposition
piece Vacater in [RBNQ]
 piece Exploiter in [RBQ] attacks Vacater
   sort "theme length"
     line 10 1000
      --> move from Vacater to _
      --> move from a to Vacater
      --> not move from Exploiter+
      --> move from Exploiter
      --> ray (Start:Exploiter
               Start:Vacater
	       Exploiter)
      
