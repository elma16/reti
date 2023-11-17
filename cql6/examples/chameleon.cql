cql (input hhdbvi.pgn)
echo (source target){
 source≺target
 sidetomove==source:sidetomove
 #◭==source:#◭
 light ♔ and source:dark ♔ 
 or dark ♔ and source:light ♔
 DeltaRank=source:rank ♔ - rank ♔
 DeltaFile=source:file ♔ - file ♔
 square all Piece in ◭
     piecename Piece ==
      source:piecename
         up DeltaRank
	      right DeltaFile
 	            Piece
}
  