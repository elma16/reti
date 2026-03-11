/*Pillsbury's mate[22] is a common method of checkmating and is named for
Harry Nelson Pillsbury.
It works by attacking the king with the rook while the bishop is
cutting off the king.[23]
It is very similar to Morphy's Mate, in fact in some ways
they are interchangeable,
the main difference is that in Pillsbury's mate, the bishop could be on h6.
*/
cql()
⬓{btm mate
R -> k
_<-k == 2

square all x in _ <- k
       (B -> x) or (R -> x)}
