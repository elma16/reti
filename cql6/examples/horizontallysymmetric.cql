/* Winning positions with more than 3 pieces that are symmetric
   when colors are swapped and the board is flipped about the
   horizontal bisector, sorted by number of pieces.
*/
   
cql(input hhdbvi.pgn result 1-0)

square all Square in .
 colortype Square ==
     -colortype
         makesquare (file Square
	             8 - rank Square + 1)

sort "npieces" [Aa] >= 4

