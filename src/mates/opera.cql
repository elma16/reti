/*It works by attacking an uncastled king on the back rank
with a rook using a bishop to protect it. An enemy pawn or
a piece other than a knight is used to restrict the enemy
king's movement.

Rook attacks king
King attacks rook
*/

cql()
⬓{btm mate
R->k
k->R
B->R}

/*
square all x in _ <- k
       (B -> x) or (R -> x)
*/
