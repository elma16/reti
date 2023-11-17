/************
This CQL file illustrates searching for certain game-level information.
It seeks games at the site "Skopje" in any event with the string "Open"
It only looks for games that Ivanchuk won against a player rated at least 2000
It sorts the result by opponent elo and year, where the year is after 1900

[Note: there are no examples in the sample database]
************/

cql (input hhdbvi.pgn)
site "Skopje"
event "Open" 
initial
⬓
  {player  white "Ivanchuk"
   sort "Opponent ELO" elo black ≥ 2000
   result 1-0}
   sort "Year" year ≥ 1900


