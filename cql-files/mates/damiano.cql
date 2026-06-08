/*
Damiano's mate is a classic method of checkmating and one of the oldest. It works by confining the king with a pawn and using a queen to execute the checkmate. Damiano's mate is often arrived at by first sacrificing a rook on the h-file, then checking the king with the queen on the a-file or h-file, and then moving in for the mate.
*/

cql() mate flipcolor shift flip {
    kg8 rf8 Qh7 pg7 Pg6
}
