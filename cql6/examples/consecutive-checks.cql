/********
Find games with at least 5 consecutive checks,
sorted by the number of consecutive checks
**********/

cql(input hhdbvi.pgn)
sort "number of consecutive checks"
  ⊢ nestban
    ―― check{5,}
