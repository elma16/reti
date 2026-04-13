// Rook homerun (consecutive rook moves to all four corners in a fixed order).

cql(
  input "path/to/games.pgn"
  output "output/rook-homeruns.pgn"
  quiet
)

flipcolor

path focus R piecepath nestban
  -- to a1
  -- to h1
  -- to h8
  -- to a8
sort "rook homerun length" pathcount
comment("Rook homerun via corners a1-h1-h8-a8")
