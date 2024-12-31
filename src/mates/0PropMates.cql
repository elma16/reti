/*
The aim of this script is to break down the proportion of checkmate patterns.
*/

cql()

if mate {
    persistent ismate += 1
    persistent matched_pattern = 0

    ;; anastasia
    if flipcolor shift flip {Ne7 pg7 Rh5 kh7} {
        persistent anastasia += 1
        matched_pattern += 1
    }

    ;; anderssen
    if ⬓{btm mate R -> k k -> R} {
        persistent anderssen += 1
        matched_pattern += 1
    }

    ;; arabian
    if ⬓{btm mate R -> k k -> R N -> R _ <- k == 2} {
        persistent arabian += 1
        matched_pattern += 1
    }

    ;; back rank
    if ⬓{btm mate (R -> k or Q -> k) _ <- k == 2} {
        persistent backrank += 1
        matched_pattern += 1
    }

    ;; balestra
    if ⬓{btm mate B -> k square all x in _ <- k (B -> x) or (Q -> x)} {
        persistent balestra += 1
        matched_pattern += 1
    }

    ;; Bishop and Knight Mate
    if ⬓{btm mate [Aa] == 4} {
        persistent bishopknight += 1
        matched_pattern += 1
    }

    ;; blackburne
    if ⬓{btm mate B -> k square all x in _ <- k (B -> x) or (N -> x)} {
        persistent blackburne += 1
        matched_pattern += 1
    }

    ;; blind swine
    if flipcolor shift flip {rf8 kg8 Rg7 Rh7} {
        persistent blindswine += 1
        matched_pattern += 1
    }

    ;; boden
    if flipcolor shift flip {kc8 rd8 pd7 Ba6 Bf4} {
        persistent boden += 1
    }

    ;; corner
    if flipcolor shift flip {Nf7 kh8 ph7 Rg1-7} {
        persistent corner += 1
        matched_pattern += 1
    }

    ;; damiano's bishop
    if ⬓{btm mate Q -> k k -> Q B -> Q} {
        persistent damianobishop += 1
        matched_pattern += 1
    }

    ;; double bishop
    if ⬓{btm mate [Aa] == 4 B == 2} {
        persistent doublebishop += 1
        matched_pattern += 1
    }

    ;; double knight
    if ⬓{btm mate N == 2 [Aa] == 4} {
        persistent doubleknight += 1
        matched_pattern += 1
    }

    ;; dovetail / cozio
    ;; if flipcolor shift flip {Qf2 kg2 [a]h1 [a]h3 * attackedby k == 5 and A attacks (* attackedby k) == 1} {
    ;;     persistent dovetail += 1
    ;; }

    ;; epaulette
    if ⬓{btm mate [R]} {
        persistent epaulette += 1
        matched_pattern += 1
    }

    ;; greco
    if ⬓{btm mate Q -> k square all x in _ <- k (B -> x) or (Q -> x)} {
        persistent greco += 1
        matched_pattern += 1
    }

    ;; hook
    if ⬓{btm mate R -> k k -> R N -> R k -> N P -> N} {
        persistent hook += 1
        matched_pattern += 1
    }

    ;; kill box
    if ⬓{btm mate R -> k k -> R not k -> Q Q -> R} {
        persistent killbox += 1
        matched_pattern += 1
    }

    ;; ladder
    if ⬓{btm mate R -> k _ <- k == 5} {
        persistent ladder += 1
        matched_pattern += 1
    }

    ;; legal
    if flipcolor shift flip {Nd5 Ne5 Bf7 ke7} {
        persistent legalmate += 1
        matched_pattern += 1
    }

    ;; lolli
    if flipcolor shift flip {kg8 Qg7 Pf6} {
        persistent lolli += 1
        matched_pattern += 1
    }

    ;; max lange
    if ⬓{btm mate Q -> k square all x in _ <- k (B -> x) or (Q -> x)} {
        persistent maxlange += 1
        matched_pattern += 1
    }

    ;; mayet/opera
    if flipcolor shift flip {kg8 Rh8 Bb2} {
        persistent mayet += 1
        matched_pattern += 1
    }

    ;; morphy
    if flipcolor shift flip {Bf6 Rg1 kh8} {
        persistent morphy += 1
        matched_pattern += 1
    }

    ;; pillsbury
    if ⬓{btm mate R -> k _<-k == 2 square all x in _ <- k (B -> x) or (R -> x)} {
        persistent pillsbury += 1
        matched_pattern += 1
    }

    ;; reti
    if flipcolor shift flip {Bd8 Rd1-5 kc7} {
        persistent reti += 1
        matched_pattern += 1
    }

    ;; smothered
    if ⬓{btm mate not k -> [A_]} {
        persistent smothered += 1
        matched_pattern += 1
    }

    ;; suffocation
    if flipcolor shift flip {Ne7 Bc3 kg8} {
        persistent suffocation += 1
        matched_pattern += 1
    }

    ;; swallowtail
    if ⬓{btm mate Q -> k k -> Q _ <- k == 5} {
        persistent swallowtail += 1
        matched_pattern += 1
    }

    ;; triangle
    if flipcolor shift flip {Qd6 Rd8 ke7 pf7} {
        persistent triangle += 1
        matched_pattern += 1
    }

    ;; vukovic
    if flipcolor shift flip {Re7 Ne6 ke8} {
        persistent vukovic += 1
        matched_pattern += 1
    }

    ;; damiano
    if flipcolor shift flip {kg8 rf8 Qh7 pg7 Pg6} {
        persistent damiano += 1
        matched_pattern += 1
    }

    ;; david and goliath
    if ⬓{btm mate P -> k} {
        persistent davidgoliath += 1
        matched_pattern += 1
    }

    ;; opera
    if ⬓{btm mate R->k k->R B->R} {
        persistent opera += 1
        matched_pattern += 1
    }

    if matched_pattern == 0 {  // If no pattern was matched
        persistent unknown_pattern += 1
        message ("Unknown pattern found in position: " str(fen))
    }
}


false
