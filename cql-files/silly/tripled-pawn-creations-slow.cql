// Tripled Pawn Creations (CQL 6.2)
// 
// Finds games where a capture creates tripled pawns, i.e., a capture move
// that brings a pawn to a file that already has 2 pawns of the same color.
// Games are sorted by the total number of such tripled-pawn-creating captures.
//
// Usage: cql -i your_games.pgn tripled-pawn-creations.cql
//        (or specify output with -o output.pgn)

cql(quiet)

MinTriples = 1   // minimum number of tripled pawn creations to include game

// Count white pawn captures that create tripled pawns
// If a pawn captures to a file and that file now has 3 pawns,
// it must have had 2 before (the capturing pawn came from another file)

WhiteTripled = find count {
  (move from P capture [a] to a2-7 and Pa2-7 == 3) or
  (move from P capture [a] to b2-7 and Pb2-7 == 3) or
  (move from P capture [a] to c2-7 and Pc2-7 == 3) or
  (move from P capture [a] to d2-7 and Pd2-7 == 3) or
  (move from P capture [a] to e2-7 and Pe2-7 == 3) or
  (move from P capture [a] to f2-7 and Pf2-7 == 3) or
  (move from P capture [a] to g2-7 and Pg2-7 == 3) or
  (move from P capture [a] to h2-7 and Ph2-7 == 3)
}

// Count black pawn captures that create tripled pawns
BlackTripled = find count {
  (move from p capture [A] to a2-7 and pa2-7 == 3) or
  (move from p capture [A] to b2-7 and pb2-7 == 3) or
  (move from p capture [A] to c2-7 and pc2-7 == 3) or
  (move from p capture [A] to d2-7 and pd2-7 == 3) or
  (move from p capture [A] to e2-7 and pe2-7 == 3) or
  (move from p capture [A] to f2-7 and pf2-7 == 3) or
  (move from p capture [A] to g2-7 and pg2-7 == 3) or
  (move from p capture [A] to h2-7 and ph2-7 == 3)
}

// Total tripled pawn creations in the game
TotalTripled = WhiteTripled + BlackTripled

// Filter: only keep games with at least MinTriples tripled pawn creations
// Sort: order games by TotalTripled in descending order (most first)
MinTriples <= sort "Tripled pawn creations" TotalTripled

// Add a comment to the game showing the count
comment("Tripled pawn creations: " TotalTripled " (White: " WhiteTripled ", Black: " BlackTripled ")")