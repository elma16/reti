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
 ◭Front∊♕♖♗ ◭Back∊♕♖♗{
   FrontStart=Front
   ///"Bristol with Front: " Front " and Back: " Back
   ⊢◎Front∪Back
     Front――  ///"Front moves to " Front
               not check
     Back―― +
            Front→Back→FrontStart→from or
	    from==FrontStart and Front→Back→from
            not Front→□→Back
            ///"Thematic Bristol move from " from
            sort "length of Bristol move"
	         between(from Front) ≥ 3
   }
