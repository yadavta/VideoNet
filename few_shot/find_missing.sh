#!/bin/bash

# Usage: ./missing_items.sh big_file.txt small_file.txt

big_file="$1"
small_file="$2"

comm -23 \
  <(sed 's/[[:space:]]*$//' "$big_file" | sort) \
  <(sed 's/[[:space:]]*$//' "$small_file" | sort)

