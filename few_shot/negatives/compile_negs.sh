# WARNING: this was written by GPT

#!/bin/bash

# Check for argument
if [ $# -ne 1 ]; then
  echo "Usage: $0 <directory_with_csv_files>"
  exit 1
fi

input_dir="$1"
output_file="hard.txt"
> "$output_file"  # Clear output file in current directory

shopt -s nullglob  # Ignore unmatched globs

for file in "$input_dir"/*.csv; do
	name=$(basename "$file" .csv | tr '[:lower:]' '[:upper:]')
	echo "$name"
	{
    	echo "\n## $name ##"
    	tail -n +2 "$file"
	} >> "$output_file"
done
