;; Underpromotion finder (CQL6)
;; Matches any pawn promotion that is NOT to a queen (i.e., to a rook, bishop, or knight).
;; Works for either color via flipcolor.

cql(
  input "path/to/games.pgn"
  output "output/underpromotions.pgn"
  quiet
)

flipcolor

path title "underpromotion" verbose
  P--=[RBN]
