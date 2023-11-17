/************
The same position occurs in the source and the target flipped about
the vertical axis. Output is sorted by number of pieces,
then the number of white pieces, then the number of black pieces
*************/
cql(input hhdbvi.pgn
    gamenumber 1 10000
    variations)

echo(s t){
 s<t
 sidetomove==s:sidetomove
 ∀sq∊▦
  piecename sq == 
   s:piecename
    makesquare (8 - file sq + 1
                rank sq)
 }
sort "Number pieces" ◭≥4
sort "Number white pieces" △
sort "Number black pieces" ▲






