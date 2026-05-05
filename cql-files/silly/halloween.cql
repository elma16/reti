// Halloween Gambit: 1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6 4.Nxe5
// Detects the position after White's Nxe5 sacrifice.

cql()

move from N capture p to e5
parent: { Pe4 Pe5==0 Nc3 Nf3 Nc6 Nf6 }
