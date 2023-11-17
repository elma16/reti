/*********
Find games with at least 4 consecutive forced white moves
*********/

cql(input hhdbvi.pgn)
4≤sort "most forced moves by white"
 ⊢◎△
   ―― {parent:countmoves legal ―― == 1} +

