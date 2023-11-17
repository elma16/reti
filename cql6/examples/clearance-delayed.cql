/* Delayed clearance theme.
A white vacating piece (V) moves to an empty square.
Later, V is captured. A white exploiting piece E moves
so as to cross the square V was on originally.

There can be any number of moves by pieces other than V and E
intervening above.

The result is sorted by the number of moves by pieces other than
V and E. 
*/

cql(input hhdbvi.pgn)
◭V∊♖♗♘♕    // the Vacating piece
 ◭E∊♖♗♕→V  // the Exploiting piece
   sort "theme length" 
     ⊢◎capture V∪E max pathcountunfocused≥5
      V――□  ///"vacater moves"
      ▲×V   ///"vacater captured"
      E―― to→pathstart:V→from
            ///"exploiter moves, crossing the original location of V" pathstart:V
