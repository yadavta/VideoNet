import argparse, os, json

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--directory', required=True, type=str, help='results directory that we are going to fix')
args = parser.parse_args()
results_dir = args.directory
if not os.path.isdir(results_dir):
    raise Exception('argument passed via `-d` flag must be a directory.')

results_file = os.path.join(results_dir, 'results.json')
if not os.path.isfile(results_file):
    raise Exception('could not locate a results.json file inside the results directory.')

with open(results_file, 'r') as f:
    results = json.load(f)

old_results = results.copy()

# Fix the unparsable errors
num_errors = 0
for action_id in results:
    for clip in results[action_id]:
        if results[action_id][clip]['accurate'] == -1:
            should_be_yes = True if clip[:3] == 'pos' else False
            print(f"\n\n\tRESPONSE:", results[action_id][clip]['response'], '\n')
            print(f"\n\n\GROUND TRUTH: {should_be_yes}, {action_id}")
            new_pred = input("\t EXTRACT 'yes', 'no', or 'idk' (without quotes) FROM RESPONSE: ")
            if new_pred != 'yes' and new_pred != 'no':
                num_errors += 1
                continue
            results[action_id][clip]['pred'] = new_pred
            if (new_pred == 'yes' and should_be_yes) or (new_pred == 'no' and not should_be_yes):
                results[action_id][clip]['accurate'] = 1
            elif new_pred in set(['yes', 'no']):
                results[action_id][clip]['accurate'] = 0
            else:
                results[action_id][clip]['accurate'] = -1
            
# Derive succint from results
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
  
os.remove(results_file)
with open(results_file, 'w') as f:
    json.dump(results, f)
    f.write('\n')

succint_file = os.path.join(results_dir, 'succint.json')
if os.path.isfile(succint_file): os.remove(succint_file)
with open(succint_file, 'w') as f:
    json.dump(succint, f)
    f.write('\n')

acc, total = pos_acc + neg_acc, pos_total + neg_total
pos_rate = 100 * pos_acc / pos_total if pos_total else 0.
neg_rate = 100 * neg_acc / neg_total if neg_total else 0.
rate = 100 * acc / total if total else 0.
summary = f"""\n\t ######## SUMMARY ######## \t\n
\t Positive Clips : {pos_acc} / {pos_total} correct ( {pos_rate:.2f}% )
\t Negative Clips : {neg_acc} / {neg_total} correct ( {neg_rate:.2f}% )
\t Total          : {acc} / {total} correct ( {rate:.2f}% )

\t Num Errors     : {num_errors}\n\n
"""
print(summary)
print("\nPLEASE NOTE THAT THE SUMMARY ABOVE HAS NOT BEEN WRITTEN ANYWHERE BESIDES YOUR TERMINAL.\n")