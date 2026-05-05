// Max consecutive non-captures: orders games by the longest streak
// of consecutive non-capturing moves (either side).

cql(quiet)

sort "max consecutive non-captures"
line
  --> not move capture [Aa] {5 200}
