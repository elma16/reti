// Outpost -- https://en.wikipedia.org/wiki/Outpost_(chess)
//
// An outpost is a square on the player's 4th-7th rank that is defended by a
// friendly pawn and can never be attacked by an enemy pawn. A knight parked on
// one is the classic powerful outpost. This finds positions where a knight
// stands on an outpost; flipcolor covers both colours.
//
// To look for other pieces on an outpost, change "N" below to e.g. [NB] or
// [NBR] (rooks excel on flank-file outposts, bishops on central ones).

cql()

flipcolor {
    // Is there a White knight standing on an outpost square?
    piece $n in N {

        // (1) On White's 4th-7th rank.
        $n & a-h4-7

        // (2) Defended by at least one White pawn.
        $n attackedby P

        // (3) No Black pawn can ever attack it. The squares from which a black
        //     pawn could (now, or after advancing) attack $n are the two
        //     adjacent files in front of it: start from where such a pawn would
        //     stand to attack $n (its NE/NW neighbours) and extend up the board.
        not (p & (up 0 7 ((northeast 1 1 $n) | (northwest 1 1 $n))))

        comment("Knight outpost on " $n)
    }
}
