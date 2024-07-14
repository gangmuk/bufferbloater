#!/bin/bash

config=$1
output=$2

if [ -z "$config" ] || [ -z "$output" ]; then
    echo "Usage: run_experiment.sh <config> <output>"
    exit 1
fi

./bin/bufferbloater -config ${config} -data_dir ${output} && python generate_report.py ${output}