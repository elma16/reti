/*Find black ideal stalemates, sorted by number of participating white pieces
  An ideal stalemate is a model stalemate such that each 
  white piece participates, either by attacking
  the kings field, by pinning a black piece, or by being pinned itself.
  We start by including the file modelstalemate.cql
*/
cql (input hhdbvi.pgn)
flipcolor{
btm stalemate
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

//The stuff above this line is copied from modelstalemate.cql
//Now we modify the included file from modelstalemate.cql
//to make all white pieces participate

A ==WhiteParticipants 
sort "Number of eligible participants: "
   A & WhiteParticipants
}