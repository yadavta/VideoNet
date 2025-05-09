#!/bin/bash

# List of action domains to process

ACTION_NAMES=(
    ballet
    bartending
    basketball
    bharatanatyam
    bouldering
    breakdance
    calligraphy
    cheerleading
    coffee
    cooking
    cricket
    crochet
    fencing
    figureskating
    football
    gardening
    gym
    hairstyling
    icehockey
    juggling
    knots
    neuroabnorm
    neurotests
    painting
    parkour
    penspinning
    pottery
    salsa
    sewing
    skateboarding
    soccer
    spamassage
    suturing
    tapdance
    tattooing
    tennis
    whittling
    yoyo
)

# Maximum number of parallel processes
MAX_PARALLEL=16

# Counter for active processes
count=0

# Function to run a command for a single action
OUTPUT="benchmark/output/action_recognition/hard_negatives_gpt4_5_o3_refinement_v4/"
run_action() {
    local action_name=$1
    echo "Running action: $action_name"
    
    python -m benchmark.action_recognition.create_negatives.gpt \
        --prompt hard_negatives_gpt4_5_o3_refinement \
        --action "$action_name" \
        --action_list "benchmark/data/action_lists/${action_name}.txt" \
        --action_definition "benchmark/data/action_definitions/${action_name}.txt" \
        --debug \
        --output_file "${OUTPUT}/${action_name}.json" &
    
    # Store the PID of the last background process
    local pid=$!
    echo "Started process for $action_name with PID: $pid"
    return $pid
}

# Make sure output directory exists
mkdir -p "$OUTPUT"

# Enable command echoing
set -x

# Array to keep track of PIDs
pids=()

# Process all actions
for action_name in "${ACTION_NAMES[@]}"; do
    # Check if we're at the max parallel limit
    if [ $count -ge $MAX_PARALLEL ]; then
        # Wait for any process to finish
        wait -n
        # Decrement counter
        ((count--))
    fi
    
    # Run the action and capture its PID
    run_action "$action_name"
    pids+=($!)
    
    # Increment counter
    ((count++))
done

# Wait for all remaining processes to complete
wait

echo "All actions completed!"