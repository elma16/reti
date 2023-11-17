/* Similar to most-visited-square-1, except comments the
  actual most visited square
*/

cql(input hhdbvi.pgn)
initial
V ∊ ▦
 sort "max number of visits to a single square"{
   ///"The most visited square is: " V
   find all
      ――V
  }≥15