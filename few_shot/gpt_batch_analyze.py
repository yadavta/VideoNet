from collections import defaultdict
import json, argparse, os

parser = argparse.ArgumentParser()
parser.add_argument('-o', '--outdir', required=True, type=str, help='Local path to directory where `batchout.jsonl` is stored.')
args = parser.parse_args()
out_dir = args.outdir

if not os.path.isdir(out_dir):
    print(f'Could not find a directory at {out_dir} ... Exiting!')
    exit(1)
out_jsonl = os.path.join(out_dir, 'batchout.jsonl')
if not os.path.isfile(out_jsonl):
    print(f'Could not find a file at {out_jsonl} ... Exiting!')

with open(out_jsonl, 'r') as f:
    lines = f.readlines()
lines = [json.loads(l) for l in lines]

# utility to extract model's prediction from model's response
def extract_prediction(text: str) -> str:
    pred = text.splitlines()[-1].strip().lower()
    pred = pred.replace('*', '').replace('#', '').replace(',', '').replace('.', '').replace(':', '')
    parts = pred.split(' ')
    if pred == "yes" or pred == "no": return pred
    if len(parts) > 1:
        first, last = parts[0], parts[-1]
        if first == 'yes' or first == 'no': return first
        elif last == 'yes' or last == 'no': return last
    if "boxed{yes}" in pred: return "yes"
    if "boxed{no}" in pred: return "no"
    if "does not show" in pred or "does not depict" in pred: return "no"
    if "the answer is yes" in pred: return "yes"
    if 'is "yes"' in pred: return "yes"
    if 'is "no"' in pred: return "no"
    return pred

# utility to compare model prediction against ground truth
def check_correct(prediction: str, expected: bool) -> int:
    pred = prediction.strip().lower()
    if expected:
        return 1 if pred == 'yes' else (0 if pred == 'no' else -1)
    else:
        return 1 if pred == 'no' else (0 if pred == 'yes' else -1)

# Convert to standard results.json format
results: dict[str, dict] = defaultdict(dict)
print()
for l in lines:
    question_id: str = l['custom_id']
    id_parts = question_id.split('-')
    if len(id_parts) != 3 or id_parts[1] not in {'pos', 'neg'}:
        print(f"\tERROR: Incorrectly formatted custom ID: {question_id}. Please investigate.")
        continue
    action_id, pos_or_neg, num = id_parts
    is_positive = True if pos_or_neg == 'pos' else False
    
    res = l['response']['body']
    if res['status'] != 'completed':
        print(f"\tERROR: Response ID {res['id']} has status {res['status']} with error {res['error']}")
        continue
    res_content = res['output'][-1]['content']
    if len(res_content) != 1:
        print(f"\ttERROR: Recieved multiple responses for Response ID {res['id']}. Please investigate.")
        continue
    res_content = res_content[0]
    
    res_text = res_content['text']
    try:
        pred = extract_prediction(res_text)
    except Exception as e:
        print(f"\ttERROR: Response ID {res['id']} gave a response of '{res_text}' ... Skipping.")
        continue
    accurate = check_correct(pred, is_positive)
    key, val = f'{pos_or_neg}{num}', {'accurate': accurate, 'prediction': pred, 'response': res_text}
    results[action_id].update({key: val})

# Calculate usage and cost
costs: dict[str, tuple[float, float]] = {'gpt-4.1-2025-04-14': (1., 4.), 'gpt-4o-2024-11-20': (1.25, 5.)}
model = lines[0]['response']['body']['model']
if model not in costs:
    print(f"Using model {model} but no cost info found for it. Please update the `costs` dictionary with this model's input and output cost.")
    exit(1)
input_rate, output_rate = costs[model]
input_count, output_count = 0, 0
for l in lines:
    input_count += l['response']['body']['usage']['input_tokens']
    output_count += l['response']['body']['usage']['output_tokens']
input_cost = input_count / 1000000. * input_rate
output_cost = output_count / 1000000. * output_rate
total_cost = input_cost + output_cost

# Create a succint version of results for easy analysis
succint: dict[str, dict] = {}
pos_acc, neg_acc, pos_total, neg_total = 0, 0, 0, 0
for id in results.keys():
    result = results[id]
    pacc, nacc, ptotal, ntotal = 0, 0, 0, 0
    i = 1
    while f'pos{i}' in result or f'neg{i}' in result:
        if f'pos{i}' in result:
            ptotal += 1
            if result[f'pos{i}']['accurate']: pacc += 1
        if f'neg{i}' in result:
            ntotal += 1
            if result[f'neg{i}']['accurate']: nacc += 1
        i += 1
    succint[id] = {'acc': pacc + nacc, 'total': ptotal + ntotal, 
                   'pos_acc': pacc, 'pos_total': ptotal,
                   'neg_acc': nacc, 'neg_total': ntotal}
    pos_acc, neg_acc = pos_acc + pacc, neg_acc + nacc
    pos_total, neg_total = pos_total + ptotal, neg_total + ntotal
    
try:
    # Generate a text summary for even easier analysis
    acc, total = pos_acc + neg_acc, pos_total + neg_total
    pos_rate = 100 * pos_acc / pos_total if pos_total else 0.
    neg_rate = 100 * neg_acc / neg_total if neg_total else 0.
    rate = 100 * acc / total if total else 0.
    summary = f"""\n\t ######## SUMMARY ######## \t\n
    \t Positive Clips  : {pos_acc} / {pos_total} correct ( {pos_rate:.2f}% )
    \t Negative Clips  : {neg_acc} / {neg_total} correct ( {neg_rate:.2f}% )
    \t Total           : {acc} / {total} correct ( {rate:.2f}% )
    
    \t Model           : {model}
    
    \t # Input Tokens  : {input_count}
    \t # Output Tokens : {output_count}
    \t Cost            : ${total_cost:.2f}
    \n\t ######## END TRANSMISSION ######## \t\n"""
except Exception as e:
    print('\n', e, '\n')
    summary = 'an error occured'

# Write processed outputs
results_path = os.path.join(out_dir, 'results.json')
succint_path, summary_path = os.path.join(out_dir, 'succint.json'), os.path.join(out_dir, 'summary.txt')

with open(results_path, 'w') as f:
    json.dump(results, f)
with open(succint_path, 'w') as f:
    json.dump(succint, f)
with open(summary_path, 'w') as f:
    f.write(summary)

print(summary)