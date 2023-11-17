/**************
In the mainline, white moves a Knight to fork the black King and a
black pawn on the second rank. In the variation, the fork
fails because there is a white piece on the forking square S
There are no other differences in the positions than that White piece
on that square, preventing the fork.
**************/

cql(input hhdbvi.pgn quiet variations)
 mainline wtm
 ⊢ primary
  ♘――□ S=to
       S→♚
       S→♟a-h2
       ///"white forks successfully"

 echo (source target) {
   try wtm
   S∩△
   ~(source∩target)==S ///"white cannot fork because " S " is occupied"
   }
