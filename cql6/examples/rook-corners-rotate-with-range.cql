/********
look for rook visiting the four corners
This uses rotate with a count to find games where a rook visits all corners
********/

cql( input hhdbvi.pgn )
initial
 piece Rook in R
  4==rotate90 count
       find Rook & a1




