/**********
 Queen staircase of length at least 
 To understand this, first note that "Q"
 is the square a Q is on. So e.g. in the chess initial position,
 "Q" means "d1".
 Now, "up 1 Q" is one square up from that square, so it would be
 "d2" in the chess initial position.
 Thus, "move from Q to up 1 Q" means: move the Q up one square.
 The "move from Q to right 1 Q" means: move the Q right one square.
 So the basic next just looks for a length four staircase starting in the
 up direction, then going right, then up.
 The flip makes this look for any directions, and the flipcolor for any color.
*************/

cql(input hhdbvi.pgn)

flipcolor flip 
 line
     -->   move from Q to up 1 Q
     -->   btm
     -->   move  from Q to right 1 Q
     -->   btm
     -->   move  from Q to up 1 Q
     -->   btm
     -->   move  from Q to right 1 Q

	
