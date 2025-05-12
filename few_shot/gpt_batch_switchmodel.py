import os, argparse, json, copy

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--indir', type=str, required=True, help='Local path to **DIRECTORY** whose batchin.jsonl file you want to copy')
parser.add_argument('-o', '--outdir', type=str, required=True, help='Local path to **DIRECTORY** where results from this batch will be stored')
parser.add_argument('-m', '--model', type=str, required=True, help='Name of model the NEW jsonl file will use. Examples: "gpt-4o-2024-11-20" or "gpt-4.1-2025-04-14"')
args = parser.parse_args()
in_dir, out_dir, model = args.indir, args.outdir, args.model

in_file = os.path.join(in_dir, 'batchin.jsonl')
if not os.path.isfile(in_file):
    print(f'Could not locate a file at {in_file} ... Please review the `-i` parameter ... Exiting!')
    exit(1)

os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, 'batchin.jsonl')

with open(in_file, 'r') as f:
    old_lines = f.readlines()
old_jsons = [json.loads(ol) for ol in old_lines]

new_jsons = []
for oj in old_jsons:
    nj = copy.deepcopy(oj)
    nj['body']['model'] = model
    new_jsons.append(nj)

with open(out_file, 'w') as f:
    for nj in new_jsons:
        json.dump(nj, f)
        f.write('\n')