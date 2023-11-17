/**********
Find games where one side wins,
but is down at least a queen's worth of material
for at least 5 consecutive moves,
sorted by the length of time he was down the material
**********/

cql(input hhdbvi.pgn)

⬓
 {result 1-0
  sort "#ply winner is down at least 9"
     ⊢ nestban
       ―― power▲ - power△ ≥ 9 {5,}
 }
		       

