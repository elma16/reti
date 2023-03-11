/*********
Find games with at least 20 consecutive checks by the same color
sorted by the number of consecutive checks

We just use "next2" to find 20 or more checks by the same side

If used "next" instead of "next2" then we would be looking for consecutive
checks by either side
*********/

cql(input hhdbvi.pgn)
sort "number of consecutive checks"
  line 20 100 nestban singlecolor
       --> check+
