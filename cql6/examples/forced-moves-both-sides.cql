/*********
Find games with the longest sequence of consecutive forced moves
*********/

cql(input hhdbvi.pgn)
sort "most forced moves"
 line 3 1000  nestban
    -->move legal count == 1 *
 