/**********
Print certain summary statistics about the database

Output to the console the number of games,
positions, underpromotions, wins, draws, mates and stalemates
in the database.

No games are matched in running this CQL code.
**********/

cql(input hhdbvi.pgn)
if initial 
 persistent NumberGames += 1
if stalemate 
  persistent NumberStalemates += 1
if ――=♖♗♘
  persistent NumberUnderpromotions += 1
if ――=♖ 
  persistent NumberRookPromotions += 1
if ――=♗
  persistent NumberBishopPromotions += 1
if ――=♘
  persistent NumberKnightPromotions += 1
if ――=♕
  persistent NumberQueenPromotions += 1
if ――=△
  persistent NumberPromotions += 1
if ――(enpassant)
   persistent NumberEnpassants += 1
if ――(castle)
   persistent NumberCastles += 1
if mate
  persistent NumberMates+= 1
if {initial result 1-0}{
    persistent NumberWins += 1
    persistent NumberWhiteWins+=1}
if {initial result 1/2-1/2}
   persistent NumberDraws += 1
if {initial result 0-1} {
    NumberWins+=1
    persistent NumberBlackWins+=1
    }
persistent NumberPositions +=1
false //we don't want any large pgn files output

