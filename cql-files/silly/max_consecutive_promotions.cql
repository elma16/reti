// Max consecutive promotions (CQL6)
// Orders games by the longest streak of consecutive promotions (either color).

cql(
  input "path/to/games.pgn"
  output "output/max-consecutive-promotions.pgn"
  quiet
)

flipcolor

MinPromotions = 3   // minimum streak length to keep

MinPromotions<=sort "max consecutive promotions"
  path nestban title "consecutive promotions" verbose
    -- [Pp]--=[QRBNqrnb]+
