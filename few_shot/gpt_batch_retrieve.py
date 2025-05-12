import os, argparse
from openai import OpenAI

parser = argparse.ArgumentParser()
parser.add_argument('-b', '--batchid', type=str, required=True, help='ID of batch given by `gpt_batch_launch.py`')
parser.add_argument('-o', '--outdir', type=str, required=True, help='Local path to **DIRECTORY** where results from this batch will be stored')
args = parser.parse_args()
batch_id, out_dir = args.batchid, args.outdir

# get api key
api_file = os.environ.get("OPENAI_API", "/gscratch/raivn/tanush/credentials/openai.txt")
try:
    with open(api_file, 'r') as f:
        api_key = f.read().strip()
except Exception as e:
    print("ERROR: unable to read OpenAI API Key at ", api_file)
    raise e
client = OpenAI(api_key=api_key)

# first check if the batch is done
batch = client.batches.retrieve(batch_id)
if batch.status != 'completed':
    print(batch, '\n\n')
    print(f"UPDATE: batch is not completed yet. instead, it is in the {batch.status} stage.")
    print("         please check again later!")
    exit(0)

file_response = client.files.content(batch.output_file_id)
os.makedirs(out_dir, exist_ok=True)
outfile = os.path.join(out_dir, 'batchout.jsonl')
try:
    with open(outfile, 'w') as f:
        f.write(file_response.text)
    print(f"UPDATE: outputs written to {outfile}")
    print(f"         try running `python gpt_batch_analyze.py -o {out_dir}`")
except Exception as e:
    print("ERROR: unable to write output to outfile")
    raise e