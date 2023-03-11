/**************
In the mainline, white moves a Knight to fork the black King and a
black pawn on the second rank. In the variation, the fork
fails because there is a white piece on the forking square
There are no other differences in the positions than that White piece
on that square, preventing the fork.
**************/

cql(input hhdbvi.pgn variations)
 mainline wtm
 ForkingSquare= _ & child:N
 ForkingSquare
 child:{ForkingSquare attacks k
        ForkingSquare attacks pa-h2}
 echo (source target) {
   variation wtm
   ForkingSquare in A
   ~(source&target)==ForkingSquare
   comment("The forking square in the target is: " ForkingSquare " and the source is: " source)
   }
