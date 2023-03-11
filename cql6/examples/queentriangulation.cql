/*Queen triangulation:
 The winning side loses a tempo using only queen moves,
 forcing the losing side to move a pawn.
*/

cql(input hhdbvi.pgn sort matchcount 2 1000 quiet)
flipcolor{
 result 1-0
 source=currentposition
 wtm
 line --> (move from Q-->.)+
      --> move from Q 
      --> {move from p
	   source&currentposition==.
           comment ("Match to: " source
	            " pawn to move from: " move from p)
           } 
  }