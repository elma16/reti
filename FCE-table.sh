#!/usr/bin/env bash

cql_dir="${1}"
db_dir="${2}"
output_dir="${3}"

rm -rf "${output_dir}"

mkdir -p "${output_dir}"

total_games=$(grep -o 'Result' "${db_dir}" | wc -l)

for filepath in src/FCE/*.cql; do

    filename=$(basename -- "$filepath")
    filename_noext="${filename%.*}"

    "${cql_dir}" -i "${db_dir}" -o "${output_dir}"/"$filename_noext".pgn \
        -matchcount 2 100  "$filepath"
    grep -o 'Result' "${output_dir}"/"$filename_noext".pgn |
        wc -l >> "${output_dir}"/number_of_games.txt
done

# calculate statistics

awk -v c=${total_games} '{for (i = 1; i <= NF; ++i) $i /= (c / 100); print }' OFS='\t' ${output_dir}/number_of_games.txt > ${output_dir}/stats.txt
