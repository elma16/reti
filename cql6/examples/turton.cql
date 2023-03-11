/*************
This example code finds Turtons (including Lloyd-Turton and Brunner-Turton).

At the start of the Turton, there are two line pieces (i.e. Q, R or B).
Each attacks a key square, called the critical square.

We call these two line pieces Front and Side, because they move in different
directions and because Front will move first.

The idea of the Turton is that instead of the Side piece just moving immediately
onto the critical square - which would seem natural, as that is where it wants to
go, first the Front piece crosses the critical square. Only
after the crossing does the Side piece then move onto the critical square (from
a different direction).

By doing so, the Front piece and the Side piece from a battery, one that has the
exact opposite orientation to the battery that would be formed had the Side piece
moved first, before the Front piece crossed.

A discussion of the code can be found in the documentation for the line filter.
***************/

cql (input hhdbvi.pgn quiet)
 piece Front in move from  [QRB] to _
    piece Side in [QRB] &~Front
     square CriticalSquare in between (Front
                                       move to . from Front){
      CriticalSquare attackedby Side
      comment("Turton with Front: " Front " Side: " Side " critical square: " CriticalSquare)
      line -->  move from Front
                 comment ("Front moves to " Front
		           " crossing critical square "
			   CriticalSquare)
           -->  not xray (Front CriticalSquare Side)
           -->  not move from (Front | Side) *
	   -->  move from Side to CriticalSquare
	          comment ("Side moves to the critical square: " CriticalSquare)
           -->  not move from (Front | Side) *
	   -->  move from Side
	           comment ("Side moves to " Side
		            " while supported by " Front)
	   -->  xray (Front CriticalSquare Side)
     }

 
