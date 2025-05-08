import argparse, sqlite3, json, os
from copy import deepcopy
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument('-m', '--master', type=str, required=True, help='Local path to master DB.')
parser.add_argument('-n', '--negatives', type=str, required=True, help='Local path to text file containing negatives (begin each domain with a line that contains "## domain_name ##" \
                    and then each line should include a comma-seperated list of length 4, where first item in list is action and the others are negatives for that action.)')
parser.add_argument('-k', '--num_context', type=int, required=True, help='Number of in-context examples to show. Must be 0 <= k <= 3.')
parser.add_argument('-o', '--output_file', type=str, required=True, help='Local path for where benchmark will be saved (as a JSON file).')
args = parser.parse_args()
master, negfile, k, outfile = args.master, args.negatives, args.num_context, args.output_file
if k not in set([0, 1, 2, 3]):
    raise Exception("ERROR: k must be 0, 1, 2, or 3.")
def make_dicts(cursor, row): return dict((cursor.description[idx][0].lower(), value) for idx, value in enumerate(row))
def serialize(domain: str, action: str) -> str: return f"{domain}.|.{action}"

# Extract all actions from master DB
mconn = sqlite3.connect(master)
mconn.row_factory = make_dicts
res = mconn.execute('SELECT id, name, domain_name, subdomain, definition FROM Actions').fetchall()
if not res:
    raise Exception("ERROR: unable to extract actions from master DB")
actions: dict[int, dict] = {}
inverse_actions: dict[str, int] = {}
for r in res:
    actions[r['id']] = {'name': r['name'], 'domain': r['domain_name'], 'subdomain': r['subdomain'], 'definition': r['definition']}
    inverse_actions[serialize(r['domain_name'].upper(), r['name'])] = r['id']

# Extract negatives from text file
with open(negfile, 'r') as f:
    lines = f.read().splitlines()
negatives: dict = {}
curr_domain = None
for l in lines:
    if l[:2] == '##':
        curr_domain = l.split('##')[1].strip()
    elif curr_domain:
        four: list[int] = [inverse_actions[serialize(curr_domain, a)] for a in l.split(',')]
        negatives[four[0]] = four[1:]
    else:
        raise Exception("ERROR: domain is not specified.")

# Extract clips from master DB
res = mconn.execute('SELECT uuid, action_id, url FROM Clips WHERE rating > -3 ORDER BY action_id, rating, id ASC').fetchall()
if not res:
    raise Exception("ERROR: unable to extract clips from master DB")
clip: dict[str, dict] = {}
actions_to_clips: dict[int, list] = defaultdict(list)
for r in res:
    clip[r['uuid']] = {'url': r['url'], 'action_id': r['action_id']}
    actions_to_clips[r['action_id']].append(r['uuid'])

# Pair actions with clips
benchmark: dict[int, dict] = {}
total = 0
used_uuids = set()
for id in actions.keys():
    relevant_clips = actions_to_clips[id]
    if len(relevant_clips) < 5:
        print(f"Skipping over action '{actions[id]['name']}' (id: {id}) since it only has {len(relevant_clips)} clips.")
        continue
    tmp = {'action': actions[id]['name'], 'domain': actions[id]['domain'], 'subdomain': actions[id]['subdomain']}
    tmp['in_context'] = relevant_clips[:k]
    tmp['positives'] = relevant_clips[3:5]
    neg1, neg2, neg3 = negatives[id]
    nn1, nn2, nn3 = actions[neg1]['name'], actions[neg2]['name'], actions[neg3]['name']
    tmp['negatives'] = [{'action_id': neg1, 'action_name': nn1, 'uuid': actions_to_clips[neg1][0]}, 
                        {'action_id': neg2, 'action_name': nn2, 'uuid': actions_to_clips[neg2][0]}]
    benchmark[id] = deepcopy(tmp)
    total += len(tmp['positives']) + len(tmp['negatives'])
    [used_uuids.add(c) for c in relevant_clips[:5]]
    [used_uuids.add(actions_to_clips[c][0]) for c in negatives[id]]
print()

# Write output files
with open(outfile, 'w') as f:
    json.dump(benchmark, f)
    
used_urls = [clip[u]['url'] for u in used_uuids]
dlfile = os.path.join(os.path.dirname(outfile), 'dl_' + os.path.basename(outfile))
with open(dlfile, 'w') as f:
    json.dump(used_urls, f)

print(f"Benchmark written to {outfile} with {total} binary questions covering {len(benchmark)} actions. Intended for a {k}-shot setup.")
print()
