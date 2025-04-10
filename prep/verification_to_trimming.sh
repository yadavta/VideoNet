#!/bin/bash

# Slurm Config

#SBATCH --job-name=prepTrimming
#SBATCH --array=0-31
#SBATCH --output=array_%A_%a.out
#SBATCH --error=array_%A_%a.err
#SBATCH --time=01:00:00
#SBATCH --mem=1G
#SBATCH -c 2

# Parameters for this batch (**MUST BE CHANGED BY YOU**)
DOMAIN='skateboarding'
export DATABASE="${DOMAIN}.db"
export JSONL="${DOMAIN}.jsonl"
export GCS="gs://action-atlas/public/${DOMAIN}/"
export TMPDIR="tmp_$(date '+%m%d_%H%M%S')"          # change this if you want to continue an old run
export OVERWRITE=0  # boolean

# Basic logging
echo "My Task ID: " $SLURM_ARRAY_TASK_ID
export NUM_TASKS=$((SLURM_ARRAY_TASK_MAX - SLURM_ARRAY_TASK_MIN))
echo "Number of Parallel Tasks: " $NUM_TASKS

# Kick off Python script to do this node's chunk of the work