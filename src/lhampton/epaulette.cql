// Epaulette mate.
// Pieces located relative to the king's position.
cql() mate flipcolor {
  // Locate the king and his epaulettes.
  ka-h8  horizontal 1 k & r == 2
  // King's field on adjacent rank are all empty or hold
  // a double epaulette.
  _ attackedby k == 3  or  p attackedby k == 2
  // The queen (and only the queen) checks.
  down 2 6 k & Q attacks k  and  A attacks k == 1
  // Only the queen guards any of the flight squares.
  A attacks (_ attackedby k) == 1
}