// Knight tour analyzer:
// - Finds the longest simple path (no square is revisited) traced by a single knight.
// - Sorted by tour length (longest first).
// - Edit the path range (currently 6-63 moves) to change min/max; set both to 63 for full tours only.

cql(
  input "path/to/games.pgn"
  output "output/knight-tours.pgn"
  quiet
)

flipcolor
Seen=[]

[Aa]KT = N--(from)
{
  Seen = []               // reset per knight
  Seen = Seen|KT          // start square is already visited
  sort "knight tour length (moves)"
    path focus KT title "knight tour" verbose nestban piecepath
      -- not to&Seen
         Seen = Seen|to
         TourMoves = pathcount
    {60,63}
}
