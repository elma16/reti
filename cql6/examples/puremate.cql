/*******
Find positions where black is in pure mate. 

There are numerous mutually incompatible definitions of "pure mate"
published and on the internet. To begin the process of determining the
best definition, we use the following motivation (from British Chess
Magazine, August, 1898), defining a "clean mate" as:
-------
    a mate in in which there is no unnecessary attack by the mating side
    on a square in the mated King's field or the king itself.
------
The key here is that each (a) *attack* must be (b) *necessary*.

The first point is (a): we are looking at *attacks* by the attacking
side. Some authors have suggested in their definitions that it is the
attacking *piece* that must be necessary in some cases, or in one case
the attacking *move*. We disagree: we think it is  more
intuitive to consider actual attacks, rather than the piece causing the
attacks or the move leading to the attack. (By contrast, in model mates
we do consider the necessity of a piece itself).

The second point is (b): the attack must be *necessary*. Many authors allow
any number of attacks on attacking pieces in the king's field. For
example, consider the following position:

White: Kh1 Qh7 Bg6 Rh2 Ng5
Black: kh8

Here, black is in mate from the queen on h7. Each empty square in the
king's field is guarded once.  But the queen on h7 is attacked three
times: by a bishop on g6, by a rook on h2, and by the knight on g5.
Obviously, these attacks are "unnecessary" so the position should not
be pure mate. Calling this pure mate in our view is not consistent
with the early definitions and also not with the spirit of term. It
just doesn't make intuitive sense in our opinion to allow a mate with
so much superfluous attacking force and call that pure.

Despite this, two widely available sources  allow this kind
of mate: the Oxford Companion to Chess (2d) edition ("unoccupied
squares in the king's field are attacked once only") and Wikipedia
("all vacant squares in the king's field are attacked only once", last
visited 10 September 2018, citing the Oxford Companion to Chess). We
doubt very much that the Oxford Companion even intended to exempt
attacking pieces in the king's field from being defended multiple
times by pieces of their own color. 

We therefore take our definition of "pure mate" from the Encyclopedia
of Chess Problems. We believe that in most cases this is a more
authoritative source: for one thing it is exclusively focused on
problem themes. It goes into far more detail and has far more themes
than either Wikipedia or the Oxford Companion. More important, the
Encyclopedia of Chess Problems' definition simply makes more sense to
us:
-----
Mate is called pure when there is only one guard or block on each
square in the (mated) King's field. Double check is allowed if the
mate could be parried without it. A pin-mate is allowed if pinning is
needed in mate.
----
Note the key change of the word "attack" in Oxford Companion and
Wikipedia to the word "guard". This difference is significant in the
cases like the following:

White: Ke6 Ra8 
Black: ke8

Here, the square f8 is not "attacked" at all. Therefore, under the
definition in the Oxford Companion (requiring squares to be attacked
"once only"), this would *not* be pure mate; neither would it be pure
mate under Wikipedia.  Those sources do not allow squares in the king's field
to be attacked 0 times. Again, we are sure this omission is
unintentional, but it is there.

Wikipedia and the Oxford Companion diverge from one another in the case of
double check. Wikipedia does not mention double check. The Oxford
Companion states that in a pure mate, "the mating move is not a double
check unless this is necessary to prevent the defender from
interposing a man or capturing a checking piece."

Under the Oxford definition, there might be two identical positions, one of
which is a pure mate, and one of which is not, depending only on the
previous move (for example, if the previous move captured a piece that
would otherwise have interposed). We again concur with Encyclopedia of
Chess Problems and with the British Chess Magazine that pure mate
should be based on the position itself, not on the move history
leading up to it. Here, even Wikipedia does not quote this definition,
although the Oxford Companion is the only cited reference.

This motivates our treatment of double check, following the Encyclopedia
of Chess Problems:

We preliminarily say that a white piece x *guards* a square y in the
Black King's field (which we define to exclude the king itself) if
either

 (1) x attacks y, or
 (2) x would attack y if the black king were on y

For example, in the position:
  W: Ke6 Ra8
  B: Ke8

The white rook on a8 guards (but does not attack) f8.

The conditions then are:

 1. Every empty square in the King's field is guarded exactly once
 2. Every square with a white piece in the King's field is guarded
 exactly once
 3. Every square with a black piece in the King's field is either
    unguarded or guarded once by a necessary pin

A necessary pin is a pin whose absence would allow the pinned piece
either to affect the mate, either by interposing between a checker and
the king, or by capturing a checker.  Thus, if the king is in double
check, there are no necessary pins.

Finally, double check is allowed only if the double check itself is
necessary, which we interpret to mean that each check could be refuted
if not for the other check, where "refuted" means that its checker
could be captured or prevented by interposition. (Of course, the mate
can never be refuted by moving the black king, because removing just a
check does not change the king's flight squares).  The phrase "if not
for the other check" means that only the attack on the king's square
by that checker is counterfactually eliminated in determining whether
a black piece could interpose.

=======================
Implementation Notes:
======================

        Global Variables:

KingsField is the squares adjacent to the black king.

Checkers is the set of checking pieces

        Functions:
	---------

GuardedSquares(x)
-----------------
 returns the set of squares in the king's field guarded by a piece x

GuardedPieces(s)
----------------
returns the set of pieces guarding a square s  

Necessary(Checker)
------------------
Here the argument Checker is a checking piece in a double check.  The
function is true if that Checker's check is necessary to the mate, in
the sense that removing the attack by Checker on the black king would
allow a (non-pinned) black piece to prevent the remaining check either
by capture or interposition

*****************/

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
        not SelfBlockerGuards
  else{ //single-check case
     not SelfBlockerGuards
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

if(Checkers>1)
  square all Checker in Checkers
   Necessary(Checker)
}