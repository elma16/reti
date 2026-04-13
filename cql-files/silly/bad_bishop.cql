// Bad bishop finder (CQL6)
// A side has a “bad” bishop if:
// - It has a bishop on that color complex.
// - Same-color pawns ≥ MinSameColorPawns and exceed opposite-color pawns by Margin.
// flipcolor makes it check both sides.

cql(
  input "path/to/games.pgn"
  output "output/bad-bishops.pgn"
  quiet
)

flipcolor

MinSameColorPawns = 4
Margin = 2

{
  HasLightB = find count { s[element]. s&light s&B }
  HasLightB >= 1
  LightP = find count { s[element]. s&light s&P }
  DarkP  = find count { s[element]. s&dark  s&P }
  LightP >= MinSameColorPawns
  LightP >= DarkP + Margin
  sort "bad bishop (light-squared)" LightP
  comment("Bad light bishop: pawns light=" LightP " dark=" DarkP)
}
or
{
  HasDarkB = find count { s[element]. s&dark s&B }
  HasDarkB >= 1
  DarkP  = find count { s[element]. s&dark  s&P }
  LightP = find count { s[element]. s&light s&P }
  DarkP >= MinSameColorPawns
  DarkP >= LightP + Margin
  sort "bad bishop (dark-squared)" DarkP
  comment("Bad dark bishop: pawns dark=" DarkP " light=" LightP)
}
