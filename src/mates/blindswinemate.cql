// Swine's mate.
cql() mate flipcolor flipvertical {
  // Place the rooks in the pattern.
  Rg-h7 == 2
  // Only the rooks participate in the mate.
  A attacks (_ attackedby k | k) == 2
  // The mating sequence ensures that the rooks are swine.
  line <-- (kg-h8 <-- move from Ra-h7 to g-h7) {2 3}
}
