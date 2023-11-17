/*This is a simple version of pure mate:
For a black pure mate:
  - Each empty square or white piece in the king's field
    is attacked at most once by white
  - Each black piece in the king's field is either unattacked by white,
    or pinned (or both)
This version calls some positions pure mates that are not (by some definitions)
actually pure mates. For example, an attack by white on a pinned black piece
is only allowed if the pin is "necessary" to the mate. Also, the way that
double checks are handled is different and fairly complex (depending on the definition).
However, these cases are rare, and the code here is simpler, so this file is adequate
for most applications

See the puremate.cql example for more detailed documentation on pure mates*/

cql (input hhdbvi.pgn)
 ⬓{
  btm mate
  ∀x∊ □△←♚
   △→x ≤ 1
  ∀x∊ (▲∩~pin)←♚
   not △→x
 }