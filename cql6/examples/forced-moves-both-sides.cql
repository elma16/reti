/*********
Find games with the longest sequence of consecutive forced moves that
are actually made

This is a rare case where the version 6.1 version is clearer. We
cannot use

 ⊢ {countmoves legal -- == 1} +

because the repetition signal '+' only applies to the right-most preceding
dash constituent, and here there are none. Likewise,

 ⊢ {countmoves legal ―― == 1}
   ―― +

would fail because the trailing '+' would only apply to the ―― .

That is why we enclose the filter and dash inside a chain. 
--
*********/

cql(input hhdbvi.pgn)
sort "most forced moves"
 ⊢ ({countmoves legal ―― == 1}
     ―― ){3,}

