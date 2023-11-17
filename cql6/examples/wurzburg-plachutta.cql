/* a version of Wurzburg-Plachutta with focus, but it found no new results
   so is not worth it really
*/

/*************
Wurzburg-Plachutta. 

Two pieces, X and Y, each move to a critical square.
each also has a unique square it must have access to for defense
Each, in separate variations, occupies the critical square, creating
a Holzhausen interference which white exploits, so that
each piece interferes with the other's ability
to access the square it needs.

*************/

cql(input hhdbvi.pgn variations result 1-0 )
mainline btm
◭X ∊ ♛♜♝
 ◭Y ∊ ♛♜♝∩~X
  C ∊ (□←X)∩(□←Y){
        // the critical square is attacked by both thematic pieces
    not X→C→Y
        // exclude unthematic cases where pieces are on the same path
    ⊢◎X∪Y
         X――C
	 X―― Y→from→X

    ⊢◎X∪Y
         Y――C
         Y―― X→from→Y
} //for each C
       
