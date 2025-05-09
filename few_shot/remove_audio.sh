#!/bin/bash

# WARNING: this code was initially written by GPT

export INPUT_DIR="audible_videos"
export OUTPUT_DIR="silent_videos"
mkdir -p $OUTPUT_DIR

printf "\n"
parallel --bar --jobs 8 '
    filename=$(basename "{}")
    output="$OUTPUT_DIR/$filename"
    if [ ! -f "$output" ]; then
        if ! ffmpeg -i "{}" -c copy -an "$output" -y -loglevel error; then
            echo "{}" >> failed_videos.txt
        fi
    fi
' ::: "$INPUT_DIR"/*

printf "\n\t #### SUMMARY #### \t\n"
echo -e "\t num of files with audio: $(ls -1 $INPUT_DIR | wc -l)"
echo -e "\t num of files w/o  audio: $(ls -1 $OUTPUT_DIR | wc -l)\n"
echo -e "\t a discrepancy in the numbers above signals a failure"
echo -e "\t a list of failures can be found at failed_videos.txt"
printf "\t #### END TRANSMISSION #### \t\n\n"
