/*********
Games with positions in which at least 3 pieces of the same color
are pinned, sorted by the number of such pinned pieces
*********/

cql(input hhdbvi.pgn quiet)
 flipcolor {
   sort "number of pinned pieces"{
	comment ("Pinned pieces: " pin through A)
	pin through A >= 3
     } 
  } // end flipcolor
 
