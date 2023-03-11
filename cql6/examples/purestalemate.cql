/*Find black pure stalemates, sorted by number of black pieces.
  A pure stalemate is a stalemate such that each square in the
  king's field is either
    (a) empty, and attacked once;
    (b) has a white piece, and is attacked once
    (c) has an unpinned black piece, and is not attacked
    (d) has a pinned black piece that is attacked once
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

sort "Number of pieces in stalemated side"
      a
}      
  

  


