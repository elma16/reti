/*********
Find games with the longest sequence of consecutive forced moves
*********/

cql(input hhdbvi.pgn)
sort "most forced moves"
 ⊢ ◎ if wtm A else a nestban
   -- {parent:countmoves legal -- == 1}
      {10,}
