import json
import os
import pandas as pd
import re

def extract_csv_from_response(response):
    """Extract CSV content from a response."""
    if not response:
        return None
    
    # Look for CSV content in the response
    csv_lines = []
    in_csv = False
    header_found = False
    
    for line in response.split('\n'):
        # Start capturing CSV content when we see the header line
        if "action,negative_1,negative_2,negative_3" in line:
            in_csv = True
            header_found = True
            csv_lines.append(line)
        # Continue capturing if we're in the CSV section and the line looks like CSV data
        elif in_csv and ',' in line and len(line.split(',')) >= 4:
            csv_lines.append(line)
        # Stop capturing if we hit a non-CSV line after starting to capture
        elif in_csv and line.strip() and ',' not in line:
            in_csv = False
    
    # If we found CSV content, join it into a string
    if csv_lines:
        return '\n'.join(csv_lines)
    return None

def check_csv(file_path, action_dir):
    """
    Check csv file has same number of actions as action list.
    Verify all positive and negative actions are in the action list.
    """
    
    # Get the domain name from the file path (without the .json extension)
    domain = os.path.basename(file_path).replace(".csv", "")

    with open(os.path.join(action_dir, f"{domain}.txt")) as f:
        action_list = [line.strip() for line in f.readlines()]
    
    is_valid = True
    try:
        # Read the csv file
        data = pd.read_csv(file_path, encoding='utf-8')
        
        # Extract CSV from the first response (initial GPT-4.5 output)
        if data.empty:
            print(f"Empty CSV file: {file_path}")
            return False
        
        # Check if the number of actions matches
        if len(data) != len(action_list):
            print(f"Number of actions in {file_path} does not match action list.")
            return False

        # Check if all actions are in the action list
        for col in data.columns:
            if col not in ["action", "negative_1", "negative_2", "negative_3"]:
                print(f"Unexpected column in {file_path}: {col}")
                is_valid = False
            
            for action in data[col].dropna().unique():
                if action not in action_list:
                    print(f"Action '{action}' in {file_path} not found in action list.")
                    is_valid = False
        
        # Lastly, check the distribution of actions throughout
        # and show warning if action has less than 3 occurrences
        # action_counts = data['action'].value_counts()
        # for action, count in action_counts.items():
        #     if count < 3:
        #         print(f"Action '{action}' in {file_path} has less than 3 occurrences: {count}.")
                
        
        return is_valid
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def process_directory(input_dir, action_dir):
    """Process all JSON files in the input directory."""
    success = 0
    failed = 0
    
    for filename in os.listdir(input_dir):
        if filename.endswith(".csv"):
            file_path = os.path.join(input_dir, filename)
            if check_csv(file_path, action_dir):
                success += 1
            else:
                failed += 1
    
    print(f"Processed {success} files successfully, {failed} files failed.")

if __name__ == "__main__":
    
    # input directory for CSV files
    action_dir = "benchmark/data/action_lists/"
    input_dir = "benchmark/output/action_recognition/hard_negatives_gpt4_5_o3_refinement_v4_csv/gpt4.5_o3_refinement"  # Change this to your desired output directory
    
    # Process all files in the input directory
    process_directory(input_dir, action_dir)
    