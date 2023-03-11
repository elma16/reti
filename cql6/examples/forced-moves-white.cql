/**********
Longest sequence of forced moves by white in a game where White wins
**********/

cql(input hhdbvi.pgn result 1-0)
wtm
sort "most forced moves by white"
  line singlecolor 4 100 nestban
    --> {move legal count == 1} *



  