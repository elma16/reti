/*********
Find all queen staircases of either color of length
at least 8 and sort the output by the length of the staircase

     matchstring ""

removes the default 'CQL' added comments, which we don't need, since
'line' adds its own comments.

The "flip" makes the staircase go in any direction The "flipcolor"
looks for both black and white queen staircases

   sort "staircase size""

just sorts the following line filter, and in the output it makes sure
that the annotations say the words "staircase size"

 'line singlecolor'

means only consider positions in which the same side is to move.
 
See the documentation for 'up' and 'right' for more discussion.


***********/

cql(input hhdbvi.pgn matchstring "")
flipcolor flip
  sort "staircase size"
   line singlecolor 8 100 nestban
   -->   (move from Q to up 1 Q
          --> move from Q to right 1 Q) +
   --> move from Q to up 1 Q ? 



