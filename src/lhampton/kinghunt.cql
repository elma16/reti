// The king hunt.
cql() terminal flipcolor { result 1-0  ka-h1-3 
  // Board congestion has never dropped below some threshold and
  // the king has never felt secure enough to go on a casual walk.
  not find <-- power [Aa] < 30 or not Q
  // Consecutive checks with a lower bound.
  sort "Checks"
  line quiet singlecolor
    <-- check {4 100}
    <-- check and posBC = currentposition and comment("CQL begin checks")
  // The king has been "drawn out" by decoys.
  sort "Decoys"
  find <-- 2 100 {
    // The "decoy" is not too far distant from the checks.
    currentposition >= posBC or distance(currentposition posBC) < 24
    move from k capture (move to . previous)
      and comment("Decoy")
  }
}