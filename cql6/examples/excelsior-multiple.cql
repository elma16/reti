/*******
This file finds games with multiple mainline excelsiors
It illustrates that the ID of a piece does not change after promotion
It sorts the result by the number of such excelsiors
*********/

cql(input hhdbvi.pgn)

initial
 1<sort "Number of excelsiors"
        ◭E ∊ ⬓♙a-h2
          find E――=△
