/* Find games where there are two parallel paths of
at least three. See 'parallelpaths.cql' for more information.
This version only comments the first 3 squares of the path,
which makes it simpler to understand perhaps.
*/

cql (input hhdbvi.pgn quiet)
piece First=move from [RrNnBbQq]  
start=currentposition
line firstmatch
   -->x=?move to . from First
         comment "Piece 1 move 1"
   -->not move from First +
   -->y=?move to ~x from First
            comment ("Piece 1 move 2")
   -->not move from First +
   -->z=?move to ~(x|y) from First
            comment ("Piece 1 move 3")

find
 line firstmatch
   --> {piece Second=move from ([RrNnBbQq]&~First) to x
                      comment "Piece 2 move 1"
        type Second==start:type First}
   --> not move from Second +
   --> move from Second to y comment "Piece 2 move 2"
   --> not move from Second +
   --> {move from Second to z comment "Piece 2 move 3"}

comment ("Parallel Paths at: x: " x" y: " y " z: " z)
