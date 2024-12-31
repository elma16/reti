// Pawn chains.
cql()
function BasePawns(S) { S & ~(S attackedby S) }
function PeakPawns(S) { S & ~(S attacks S) }

Chain = []
square BP in BasePawns(P) {
  not BP & Chain
  Chain = BP  lastChain = []
  while (Chain != lastChain) {
    lastChain = Chain
    Chain |= P attackedby Chain | P attacks Chain
  }
  Chain > 5 and BasePawns(Chain) > 1 and PeakPawns(Chain) > 2
  comment("Chain at " Chain)
}