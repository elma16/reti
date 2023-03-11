/************
Find games with at least 5 passed pawns of the same color
sorted by the number of such passed pawns
This works analogously if "passedpawns" is replaced by
"doubledpawns" or "isolatedpawns" or "connected"
To just consider white pawns, remove the "flipcolor"
**************/

cql(input hhdbvi.pgn)
flipcolor
sort "number passers"
   passedpawns&A
    >=5