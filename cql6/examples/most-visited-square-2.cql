/* Similar to most-visited-square-1, except comments the
  actual most visited square.
*/

cql(input hhdbvi.pgn)
initial
square VisitedSquare in .
 sort "max number of visits to a single square"{
   comment ("The most visited square is: " VisitedSquare)
   find all
      move to VisitedSquare
  }>=15