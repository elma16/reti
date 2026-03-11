;; Triangulation finder (CQL6)
;; Three consecutive king moves: leave the start square, visit two new squares, return to start.
;; flipcolor covers either side.
;; BROKEN

cql(
  input "path/to/games.pgn"
  output "output/triangulations.pgn"
  quiet
)

flipcolor

[Aa]T = K--(from)
{
  Seen = from
  path focus T piecepath nestban
    -- not to&Seen
       Seen = Seen|to
    -- not to&Seen
       Seen = Seen|to
    -- from
  {3,3}
  sort "triangulation (king)" pathcount
  comment("Triangulation by king")
}
