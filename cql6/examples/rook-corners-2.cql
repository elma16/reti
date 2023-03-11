/********
look for rook visiting the four corners
This is a slightly more compact version of rook-corners-1.cql
**********/

cql( input hhdbvi.pgn )
initial
 piece Rook in R
  square all Corner in rotate90 a1
   find Rook == Corner





