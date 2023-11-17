/* Winning positions with more than 3 pieces that are symmetric
   when colors are swapped and the board is flipped about the
   horizontal bisector, sorted by number of pieces.

Note:the 6.1 version is slightly shorter but use the more obscure
colortype filter, which we are trying to phase out.
*/
   
cql(input hhdbvi.pgn result 1-0)

∀S∊▦ {
 F= makesquare (file S
                8-rank S +1)
 typename F==typename S
 S∩□ or
 ⬓{S∩△ F∩▲}
 }
sort "npieces" ◭ ≥ 4

