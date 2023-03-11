/*************
Wurzburg-Plachutta. 

Two pieces, X and Y, each move to a critical square.
each also has a unique square it must have access to for defense
Each, in separate variations, occupies the critical square, creating
a Holzhausen interference which white exploits, so that
each interferes with the other's ability
to access the square it needs.
Note that "ray (X Y .)" is the set of squares Z such that there is
a ray from X to Y to Z
*************/

cql(input hhdbvi.pgn variations result 1-0 )
mainline
btm
piece X in [qrb]
 piece Y in [qrb] & ~X
  square CriticalSquare in (_ attackedby X) & (_ attackedby Y){
        // the critical square is attacked by both thematic pieces

    not CriticalSquare in between (X Y)
        // exclude unthematic cases where pieces are on the same line

    line --> move from X to CriticalSquare
         --> wtm
	 --> ray (Y X
	          move to . from X)
    line --> move from Y to CriticalSquare
         --> wtm
         --> ray (X Y
	          move to . from Y)
		  
   }     	   
       
