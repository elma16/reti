/**********
This example is based on zugzwang1.cql, the same position occurs with
black to move in the mainline, but white to move in the variation, in
a win study.  However, this also requires that the paths from the
latest common ancestor to the two positions have a sequence of at
least 5 moves in common the output is sorted by the length of the
common sequence of moves. The position must arise from a white try.
************/

cql(input hhdbvi.pgn result 1-0 variations)
 mainline btm
sort "Common consecutive move sequence"
 echo (source target){
  wtm try
  source∩target==▦
  consecutivemoves (source target)≥5
 }
 
