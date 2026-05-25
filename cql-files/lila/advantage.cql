// advantage - the solution yields a clear positional or material advantage
// Note: precise eval thresholds require engine analysis.
// This approximation finds positions with moderate material advantage.

cql()
 flipcolor {
  result 1-0
  not mate
  power A - power a >= 2
  power A - power a <= 5}

comment("advantage")
