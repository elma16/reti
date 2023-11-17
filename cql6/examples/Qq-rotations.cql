/*
Find games where a black and white Queen are separated by a single piece,
and where all eight possible orientations of this configuration of queens occurs.
Actually we find games where at least 5 of the orientations occur, sorted by the number
of orientations.

To understand this, suppose there is a Q on d4. Then
     right 1 Q
is
the square e4, and [
      [Aa] ∩ right 1 Q
will match a position with the Q on d4, and a piece on e4.

Then
     right 1 ([Aa] ∩ right 1 Q)
will be the square f4, and so
        q ∩ right 1 ([Aa] ∩ right 1 Q)

will match a position with
     the Q on d4,
     a piece on e4 and
     a q on f4.

Since this works no matter where the Q is, this matches one of the eight
orientations of the Q and q. Now when we put a rotate45
in front of this, the "right" is replaced successively by northeast, north, southwest, and so on over all    the directions. This gives us all the orientations.
*/

cql(input hhdbvi.pgn variations)
initial
 sort "Number of theme occurrences"
  {rotate45 count
   find ♛
       ∩ right 1
            (◭ ∩ right 1 ♕)}
    ≥5
