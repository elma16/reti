/***********
This CQL file illustrates searching for certain game-level information.
It seeks games with a first prize
1st prize in the Heijden database (not including ".p" prizes)
It sorts the result by the length of the study
*************/

cql (input hhdbvi.pgn)
hhdb prize == 1
terminal
sort "Length of game" movenumber 

