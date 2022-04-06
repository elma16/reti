#!/usr/bin/env bash

cql_dir="${1}"
db_dir="${2}"
output_dir="${3}"

mkdir -p "${output_dir}"

for filename in src/FCE/*.cql; do
    basename "${filename}"
    file="$(basename -- ${filename})"
    "${cql_dir}" -i "${db_dir}" -o "${output_dir}"/"$file".pgn -matchcount 2 100  "$filename"
done
