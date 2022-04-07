#!/usr/bin/env bash

# given a directory with pgn files, output
# 1) an output directory with pgn breakdown by fundamental ending
# 2) spreadsheet of statistics comparing it with megadatabase 2001

cql_dir="${1}"
db_dir="${2}"
output_dir="${3}"

rm -rf "${output_dir}"
mkdir -p "${output_dir}"

for pgnpath in "${db_dir}"/*.pgn; do
    total_games=$(grep -o 'Result' "$pgnpath" | wc -l)
    pgnname=$(basename -- "$pgnpath")
    pgnname_noext="${pgnname%.*}"
    mkdir -p  "${output_dir}"/"$pgnname_noext"

    for filepath in src/FCE/*.cql; do
        filename=$(basename -- "$filepath")
        filename_noext="${filename%.*}"
        "${cql_dir}" -i "$pgnpath" -o "${output_dir}"/"$pgnname_noext"/"$filename_noext".pgn \
            -matchcount 2 100  "$filepath"
        grep -o 'Result' "${output_dir}"/"$pgnname_noext"/"$filename_noext".pgn |
            wc -l >> "${output_dir}"/"$pgnname_noext"/number_of_games.txt
    done
# calculate statistics
awk -v c=${total_games} '{for (i = 1; i <= NF; ++i) $i /= (c / 100); print }' OFS='\t' \
    ${output_dir}/"$pgnname_noext"/number_of_games.txt > ${output_dir}/"$pgnname_noext"/stats.txt

# append text as a column to examples/FCE.csv
awk -F "," 'BEGIN { OFS = "," } {$3= ${output_dir}/"$pgnname_noext"/stats.txt ; print}' examples/FCE.csv > examples/FCE-new.csv
done

