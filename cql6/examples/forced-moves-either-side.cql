/********
most consecutive forced moves by one side
***********/

cql(input hhdbvi.pgn)
sort "most forced moves by either side"
  line singlecolor 10 100 nestban --> move legal count == 1 *



  