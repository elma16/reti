/*It works by attacking an uncastled king on the back rank
with a rook using a bishop to protect it. An enemy pawn or
a piece other than a knight is used to restrict the enemy
king's movement.

Rook attacks king
King attacks rook
*/

cql()
flipcolor{btm mate
R attacks k
k attacks R
B attacks R

square all x in _  attackedby  k
       (B  attacks  x) or (R  attacks  x)}
