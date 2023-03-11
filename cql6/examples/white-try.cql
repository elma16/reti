/***********
this illustrates how to find positions that are "white tries".
These are positions that are
in a variation, but they arise from White moving from the mainline
************/

cql(input hhdbvi.pgn variations gamenumber 1 1000 quiet)
 line <-- variation+
      <-- {mainline wtm}
 comment("white try")


