/*Find black model stalemates, sorted by number of participating white pieces
  A model stalemate is a pure stalemate such that each 
  non-king non-pawn white piece participates, either by attacking
  the kings field, by pinning a black piece, or by being pinned itself.
  We start by including the file purestalemate.cql
*/
cql (input hhdbvi.pgn)
flipcolor{btm stalemate
KingsField= . attackedby k
SelfBlockers= a & KingsField
PossibleFlightSquares= KingsField & [A_]

square all FlightSquare in PossibleFlightSquares
 #A attacks FlightSquare==1

square all SelfBlocker in SelfBlockers & pin
  #A attacks SelfBlocker==1

square all SelfBlocker in SelfBlockers & ~pin
  not A attacks SelfBlocker

//This ends the stuff copied from purestalemate.cql
//Now we check each white piece participates
//We save the set of participants so we can sort on their
//number
WhiteParticipants =
  pin through A
  | pin from A
  | A attacks KingsField

//Now for model stalemate, we only consider [RBNQ] as participants:
//For ideal stalemate, we will modify the next two lines:

[RBNQ] in WhiteParticipants 
sort "Number of eligible participants: "
   [RBNQ] & WhiteParticipants
}


  


 