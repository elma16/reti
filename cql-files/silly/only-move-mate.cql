// Only-move mate: the side delivering mate had exactly one legal move,
// and that move was the mate (forced into mating).

cql()

mate
parent: { move legal count == 1 }
