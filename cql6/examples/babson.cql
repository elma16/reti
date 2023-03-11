/*
This finds "partial Babsons".

A "Babson pair" is a black promotion followed by a white promotion to
the same piece type to which black just promoted. (The white
promotion should be the only refutation of the Black promotion).

We say two Babson pairs are "compatible" if they use the same two
pawns but different piece types to promote to.

The "Babson count" of a position is the size of the largest collection
of compatible Babson pairs in that position.

The "Babson task" is to find a position whose Babson count is 4.

In other words, there is a position in which there is a black pawn X
and white pawn Y such that if X promotes to Q, white refutes by
promoting Y to Q; if X promotes to R white refutes by promoting Y to
R; if X promotes to B then white refutes by promoting Y to B; if X
promotes to a N then white refutes by promoting Y to N.

The Babson task has never been found for a study (it has for problems).

This CQL file sorts games by their Babson count.

The function babsonpair(PieceType) increments the variable
"numberbabsons" whenever the current position has a Babson pair
promoting to Piecetype using pawns "pawn" and "Pawn".
*/

cql(input hhdbvi.pgn variations quiet)

function babsonpair(PieceType){
  if line
       --> move from pawn promote A
       --> {type pawn == PieceType
            comment("promotion to " pawn)
	    move primary // next position should be only refutation
           }
       --> {type Pawn == PieceType
            comment ("responding promotion to " Pawn)}
     numberbabsons+=1}	    

piece pawn in pa-h2
 piece Pawn in Pa-h7
  sort "Number of Babson pairs"{
    numberbabsons=0
    babsonpair(2) // Knight
    babsonpair(3) // Bishop
    babsonpair(4) // Rook
    babsonpair(5) // Queen
    comment ("Babson theme with " numberbabsons " pairs")
    numberbabsons>=2
}       
