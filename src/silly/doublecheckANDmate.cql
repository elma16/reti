;; what proportion of double checks are also checkmates?

cql()

flipcolor {
    if #(A → k) >= 2 {
        persistent double_check += 1
        if mate {
            persistent double_check_mate += 1
        }
    }
}

false
