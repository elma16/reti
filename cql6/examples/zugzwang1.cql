/*********
This simple example just illustrates how to find a zugzwang: the same position occurs with black to move in the
mainline, but white to move in the variation, in a win study
The wtm position must arise from a white try from the mainline
**********/

cql(input hhdbvi.pgn variations)
result 1-0 //white wins
mainline // current position is a mainline
btm      // black to move
/*Now we seek a target in the variations that is wtm
  with the same board position. We set source to the
  old current position, and we continually reset target
  to each other position in the game*/
echo(source target){ 
 wtm try
 source∩target==▦ //source and target have the same board position
 }
 
