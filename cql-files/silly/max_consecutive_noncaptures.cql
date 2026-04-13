// Max consecutive non-captures (CQL6)
// Orders games by the longest streak of consecutive non-capturing moves (either color).

cql(
  input "path/to/games.pgn"
  output "output/max-consecutive-noncaptures.pgn"
  quiet
)

flipcolor

MinNonCaptures = 5   // minimum streak length to keep

MinNonCaptures<=sort "max consecutive non-captures"
  path nestban title "consecutive non-captures" verbose
    -- move to .+
