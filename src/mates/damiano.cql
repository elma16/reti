cql() mate flipcolor shift flip {
    kg8 rf8 Qh7 pg7 Pg6
}
// Damiano's mate.
// Mate or resignation with imminent mate.
cql() terminal flipcolor { result 1-0
  // Establish the basic pattern.
  kg-h8 rf8 pg7 Pg6
  // Queen mates on h7 or threatens mate.
  Q attacks h8
  // A rook sacrifice at h8 preps mate with tempo.
  sort "Line length"
  line <-- .{1 6} <-- move from k capture Rh8
}
