// dovetail's mate.
// Shift and flip the pattern across the board.
cql() mate flipcolor shift flip {
  // Establish the pattern with two friendly obstructing pieces.
  Qg2 kg3 [a]f4 [a]h4
  // All other squares are empty and only the queen prevents flight.
  _ attackedby k == 5 and A attacks (_ attackedby k) == 1
} 