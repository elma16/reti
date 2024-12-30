

//cql()
//btm mate
//B -> k

//square all x in _ <- k
//       B -> x


// Boden's mate.
cql() mate flipcolor {
  // Place the king anywhere along the back rank.
  B attacks ka-h8
  // Assign sets of empty squares in king's field attacked by the bishops.
  BD = {{diagonal 1 k} & _} attackedby B
  BO = {{orthogonal 1 k} & _} attackedby B
  // Stipulate cardinality of sets and orientation of lines of attack.
  BD == 1  BO == 2  (orthogonal 1 BD) & BO == 2
  // Only the bishops are guarding or attacking the king or his escape.
  {_ attackedby k | k} attackedby [KQRNP] == 0
}
