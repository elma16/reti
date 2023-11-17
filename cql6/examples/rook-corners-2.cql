/********
look for rook visiting the four corners
This is a slightly more compact version of rook-corners-1.cql
**********/

cql( input hhdbvi.pgn )
initial
 ◭T∊♖
  ∀C∊rotate90 a1
   find T == C





