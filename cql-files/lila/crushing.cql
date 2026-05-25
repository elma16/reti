// crushing - the solution wins decisive material (no mate)
// Note: precise eval thresholds require engine analysis.
// This approximation finds positions with large material gains.

cql()
 flipcolor {
  result 1-0
  not mate
  power A - power a >= 6}

comment("crushing")
