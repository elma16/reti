/*
black ideal mate
Same as model mate (in puremate.cql), except each piece on the
board takes part.
The output is sorted by the total number of pieces in the mate.

This file begins by copying modelmate.cql, then making a few small
modifications
*/


cql(input hhdbvi.pgn)
flipcolor{mate btm

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
     or Checkers==1
        and xray (PossibleRefuter Attacker RefuterSquares)

[RNBQ] in WhiteParticipants //every piece participates
/* The code above this line is identical to modelmate.cql*/

/* Now we start on the idealmate specific stuff*/

//each white piece is a participating attacker (this could
// have been accomplished with a square all as well)

A==WhiteParticipants

//check that all black pieces participates
square all BlackPiece in a & ~(k|KingsField) {
  xray (a BlackPiece K)
  or {Checkers==1 //not a double check
      xray (a BlackPiece RefuterSquares)}
}

sort "Number Pieces in the ideal mate" [Aa]
}