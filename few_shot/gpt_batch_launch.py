import os, argparse
from datetime import datetime
from openai import OpenAI

parser = argparse.ArgumentParser()
parser.add_argument('-b', '--batchfile', type=str, required=False, help='local path to JSONL file that will be fed to the OpenAI Batch API')
parser.add_argument('-id', '--batchfileid', type=str, required=False, help='OpenAI-assigned ID of a batch file that has been previously uploaded to the OpenAI API')
parser.add_argument('-n', '--batchname', type=str, required=True, help='Name of batch; will be placed in the metadata of the batch on the OpenAI API')
args = parser.parse_args()
batch_filepath, batch_fileid, batch_name = args.batchfile, args.batchfileid, args.batchname

if not batch_filepath and not batch_fileid:
    print('You must either provide a batchfile via `-b` that will be uploaded to the OpenAI API, or the OpenAI-assigned ID of a batchfile that has already been uploaded via `-id`. Exiting!')
    exit(1)
if batch_filepath and batch_fileid:
    print('You provided both a batchfile to upload and the ID of an already-uploaded file. Please only provide one of the two. Exiting!')
    exit(1)

# get api key
api_file = os.environ.get("OPENAI_API", "/gscratch/raivn/tanush/credentials/openai.txt")
try:
    with open(api_file, 'r') as f:
        api_key = f.read().strip()
except Exception as e:
    print("ERROR: unable to read OpenAI API Key at ", api_file)
    raise e
client = OpenAI(api_key=api_key)

# read batch file
if batch_filepath:
    batch_file = client.files.create(
        file=open(batch_filepath, 'rb'),
        purpose='batch'
    )
    batch_fileid = batch_file.id
    
print('Using the following file: ', batch_fileid)

try:
    batch = client.batches.create(
        input_file_id=batch_fileid,
        endpoint='/v1/responses',
        completion_window='24h',
        metadata={
            "batchname": batch_name,
            "created": str(datetime.now().replace(microsecond=0)),
        }
    )
except Exception as e:
    print(f"\nERROR: unable to create batch")
    raise e

print("\nbatch created!")
print(f"hold onto this ID. do not lose it.\t BATCH ID: {batch.id}\n")
print("if you lose it, do `clients.batches.list()` to get a Pager and print out the first 5 elements using a for loop.\n")