import json
import os
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
            line = line.strip()
            csv_lines.append(line)
        # Continue capturing if we're in the CSV section and the line looks like CSV data
        elif in_csv and ',' in line and len(line.split(',')) >= 4:

            # Strip leading/trailing whitespace and check for valid CSV format
            line = [s.strip() for s in line.split(',')]
            line = ','.join(line)
            
            csv_lines.append(line)
        # Stop capturing if we hit a non-CSV line after starting to capture
        elif in_csv and line.strip() and ',' not in line:
            in_csv = False
    
    # If we found CSV content, join it into a string
    if csv_lines:
        return '\n'.join(csv_lines)
    return None

def process_json_file(file_path, output_dir):
    """Process a JSON file and extract CSV content from the first and last responses."""
    # Create output directories if they don't exist
    gpt_dir = os.path.join(output_dir, "gpt4.5")
    refined_dir = os.path.join(output_dir, "gpt4.5_o3_refinement")
    os.makedirs(gpt_dir, exist_ok=True)
    os.makedirs(refined_dir, exist_ok=True)
    
    # Get the domain name from the file path (without the .json extension)
    domain = os.path.basename(file_path).replace(".json", "")
    
    try:
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract CSV from the first response (initial GPT-4.5 output)
        if data and len(data) > 0:
            first_response = data[0].get("response", "")
            first_csv = extract_csv_from_response(first_response)
            
            if first_csv:
                # Save to the GPT-4.5 directory
                first_csv_path = os.path.join(gpt_dir, f"{domain}.csv")
                with open(first_csv_path, 'w', encoding='utf-8') as f:
                    f.write(first_csv)
                print(f"Saved initial CSV for {domain} to {first_csv_path}")
        
        # Extract CSV from the last response (GPT-4.5 after o3 refinement)
        if data and len(data) > 3:  # Assuming the last response is always at index 3
            last_response = data[-1].get("response", "")
            last_csv = extract_csv_from_response(last_response)
            
            if last_csv:
                # Save to the refinement directory
                last_csv_path = os.path.join(refined_dir, f"{domain}.csv")
                with open(last_csv_path, 'w', encoding='utf-8') as f:
                    f.write(last_csv)
                print(f"Saved refined CSV for {domain} to {last_csv_path}")
        
        return True
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def process_directory(input_dir, output_dir):
    """Process all JSON files in the input directory."""
    success = 0
    failed = 0
    
    for filename in os.listdir(input_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(input_dir, filename)
            if process_json_file(file_path, output_dir):
                success += 1
            else:
                failed += 1
    
    print(f"Processed {success} files successfully, {failed} files failed.")

if __name__ == "__main__":
    # Input directory containing JSON files
    input_dir = "benchmark/output/action_recognition/hard_negatives_gpt4_5_o3_refinement_v4"  # Change this to your input directory
    
    # Output directory for CSV files
    output_dir = "benchmark/output/action_recognition/hard_negatives_gpt4_5_o3_refinement_v4_csv"  # Change this to your desired output directory
    
    # Process all files in the input directory
    process_directory(input_dir, output_dir)
    
    # If you want to process just a single file, uncomment and modify the line below
    # process_json_file("json_files/figureskating.json", output_dir)