// Cozio's mate.
// Shift and flip the pattern across the board.
cql() mate flipcolor shift flip {
  // Establish the pattern with two friendly obstructing pieces.
  Qh2 kg3 [a]f3 [a]g4
  // All other squares are empty and only the queen prevents flight.
  _ attackedby k == 5 and A attacks (_ attackedby k) == 1
}
