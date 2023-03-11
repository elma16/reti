/*
black model mate, sorted by number of non-king, non-pawn white
participants.

A model mate is a pure mate with the additional requirement that each
white piece, except possibly for king and pawns takes part.

By "takes part" we mean either attacks the king's field, or gives
check, or pins a potential refuter, or obstructs a potential refuter
from attacking refutation square.  A "potential refuter" is a black
piece that could otherwise attack a "refutation square", which is the
white king, or a checker, a square between a checker and the white
king. When there is a double check, however, then we don't count pins
by white or obstructions by white other than to the white king, since
those don't affect the check.

This file begins by simply including in puremate.cql without change.
*/
cql(input hhdbvi.pgn)
flipcolor{
mate btm

KingsField= . attackedby k

Checkers= A attacks k

function GuardedSquares(x){
  KingsField attackedby x
  | xray (x k KingsField)}

function GuardingPieces(s) { 
  piece fy in A
     s & GuardedSquares(fy)}
     

// Every flight square guarded exactly once
square all FlightSquare in KingsField & [_A]
  GuardingPieces(FlightSquare)==1

//Every selfblocker is either unguarded, or, if it is not double check,
// (a) pinned and (b) could interfere with a checker

square all SelfBlocker in KingsField & a {
  SelfBlockerGuards=GuardingPieces(SelfBlocker)
  if Checkers>1 
        SelfBlockerGuards==0
  else{ //single-check case
     SelfBlockerGuards==0
     or
     {SelfBlockerGuards==1
      pin through SelfBlocker
      move pseudolegal
          from SelfBlocker
	  to   (Checkers | between (Checkers k))
     or move pseudolegal enpassant from SelfBlocker	  
     }
   } // end the single-check case
  } //end considering the SelfBlocker

function Necessary(Checker){
  OtherChecker=Checkers & ~Checker
  RefutationSquares= OtherChecker | between (OtherChecker k)
  NonPinnedBlackPiece= {a & ~pin} & ~k
  NonPinnedBlackPiece attacks RefutationSquares
}                       

if Checkers>1 
  square all Checker in Checkers
   Necessary(Checker)
/* The code above this line is identical to puremate.cql */

RefuterSquares=
  K |
  Checkers |
  between(Checkers k)

PossibleRefuter=
  move from a to RefuterSquares pseudolegal

WhiteParticipants=
  square  Attacker in A
     Attacker in Checkers
     or Attacker attacks KingsField
     or pin through Attacker
     or Checkers ==1
        and pin from Attacker through PossibleRefuter
     or Checkers ==1      
        and xray (PossibleRefuter Attacker RefuterSquares)

[RNBQ] in WhiteParticipants //every piece participates

sort "Number of eligible participating attackers: "
   [RNBQ] & WhiteParticipants
}