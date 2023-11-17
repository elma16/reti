/*********
Games with positions in which at least 3 pieces of the same color
are pinned, sorted by the number of such pinned pieces
*********/

cql(input hhdbvi.pgn quiet)
 ⬓{
   sort "number of pinned pieces"{
	///"Pinned pieces: " pin through △
	pin through △ ≥ 3
     } 
  } // end ⬓
 
