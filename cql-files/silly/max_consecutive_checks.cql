// Max consecutive checks (CQL6)
// Orders games by the longest streak of consecutive checks (either color).

cql(
  input "path/to/games.pgn"
  output "output/max-consecutive-checks.pgn"
  quiet
)

MinChecks = 3   // minimum streak length to keep

MinChecks<=sort "max consecutive checks"
  path nestban title "consecutive checks" verbose
    -- check+
