/*
Q and q are on the same file or rank, separated
by a single square with a piece on it. The configuration
recurs in all 4 possible orientations. See Qq-rotations.cql for a more general version that considers 45 degree rotations as well
*/

cql(input hhdbvi.pgn variations)
initial
 4==rotate90 count
       find shift {♕d4 ◭e4 ♛f4}

 
