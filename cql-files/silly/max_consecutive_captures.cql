// Max consecutive captures (CQL6)
// Orders games by the longest streak of consecutive captures (either color).

cql(
  input "path/to/games.pgn"
  output "output/max-consecutive-captures.pgn"
  quiet
)

flipcolor

MinCaptures = 3   // minimum streak length to keep

MinCaptures<=sort "max consecutive captures"
  path nestban title "consecutive captures" verbose
    -- move capture [Aa]+
