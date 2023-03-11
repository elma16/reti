/* 
Find games in which there is a "two-piece cycle" in which two pieces,
   piece1 (a black piece) and piece2 (a white piece), each traverse
   the same set of squares. Piece1 starts, then piece2 moves to a
   square, then piece1 moves to a new square, and so on, until each
   piece's final move ends on the same square as that piece's initial
   square.  Thus, the path of each piece forms a cycle. The moves must
   be consecutive.  Games are sorted by length of cycle.
*/   

cql (input hhdbvi.pgn)

/* The function insert_square
   takes a single square Square and a set of squares Set
   If Square is in Set, the function does not match.
   Otherwise, Square is inserted into Set. 
*/

function insert_square (Square Set){
  not Square in Set  
  Set = Square | Set // insert Square into Set
} 

piece piece1 in a 
 piece piece2 in A{ 
   initial1 =piece1 // piece1 start
   initial2=piece2  // piece2 start
   cycle1 = initial1 // piece1 cycle
   cycle2 = initial2 // piece2 cycle
   line --> move from piece1 
        --> ( insert_square(piece1 cycle1) 
                     -->
	     insert_square(piece2 cycle2) 
            ) + // repeat the pattern of the last 2 moves
        --> piece1==initial1 // piece1 completes its cycle
        --> {piece2==initial2 // piece2 completes its cycle
            cycle1 == cycle2} 

   sort "cycle length: " cycle1 
 } 

 