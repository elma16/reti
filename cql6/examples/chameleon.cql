cql (input hhdbvi.pgn)
echo (source target){
 target>source
 sidetomove==source:sidetomove
 #[Aa]==source:#[Aa]
 light K and source:dark K 
 or dark K and source:light K
 DeltaRank=source:rank K - rank K
 DeltaFile=source:file K - file K
 square all Piece in [Aa]
     colortype Piece ==
      source:colortype
         up DeltaRank
	      right DeltaFile
 	            Piece
}
  