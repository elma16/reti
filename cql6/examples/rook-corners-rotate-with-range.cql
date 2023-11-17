/********
look for rook visiting the four corners
This uses rotate with a count to find games where a rook visits all corners
********/

cql( input hhdbvi.pgn )
initial
 ◭T∊♖
  4==rotate90 count
       find T ∩ a1




