/************
Find all Bristols orthogonal or diagonal.
Here a front line piece (Front) moves to a destination.

Later, along the same line, a back line piece (Back) follows the
path of Front, crossing the same squares it does, and landing
just behind it.

The results are sorted by the length of the move
by Back (which must traverse at least 3 squares to be
included).
*************/

cql(input hhdbvi.pgn quiet)
 Start=currentposition
 piece Front in [QRB]
  piece Back in [QRB]{
   comment ("Bristol with Front: " Front " and Back: " Back)
   line
     -->  move from Front comment ("Front moves to " Front)
     -->  not check
     -->  not move from Front*
     -->  {xray (Back
                  between (Start:Front
                           Front)
		  Front)
           move from Back to
                      anydirection 1 Front
                 comment ("Thematic Bristol move from " parent:Back)
           sort "length of Bristol move"
	         between (Back Front) >= 3
            } 
   }