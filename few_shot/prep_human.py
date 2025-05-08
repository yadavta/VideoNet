import argparse, sqlite3, json, os, random
from copy import deepcopy
from collections import defaultdict

random.seed(493)

parser = argparse.ArgumentParser()
parser.add_argument('-m', '--master', type=str, required=True, help='Local path to master DB.')
parser.add_argument('-n', '--negatives', type=str, required=True, help='Local path to text file containing negatives (begin each domain with a line that contains "## domain_name ##" \
                    and then each line should include a comma-seperated list of length 4, where first item in list is action and the others are negatives for that action.)')
parser.add_argument('-d', '--database', type=str, required=False, default='human_eval.db', help='Local path to WHERE you want the new DB created.')
args = parser.parse_args()
master, negfile, edb = args.master, args.negatives, args.database

# Extract all domains from master DB
mconn = sqlite3.connect(master)
def make_dicts(cursor, row): return dict((cursor.description[idx][0].lower(), value) for idx, value in enumerate(row))
mconn.row_factory = make_dicts
res = mconn.execute('SELECT distinct domain_name FROM Actions').fetchall()
if not res:
    raise Exception('ERROR: unable to extract domains from master DB')
domains_to_actions: dict[str, list[int]] = {}
for r in res:
    domain = r['domain_name']
    domains_to_actions[domain] = []

# Extract all actions from master DB
def serialize(domain: str, action: str) -> str: return f"{domain}.|.{action}"
res = mconn.execute('SELECT id, name, domain_name, subdomain, definition FROM Actions').fetchall()
if not res:
    raise Exception("ERROR: unable to extract actions from master DB")
actions: dict[int, dict] = {}
inverse_actions: dict[str, int] = {}
domain_counts = defaultdict(int)
for r in res:
    actions[r['id']] = {'name': r['name'], 'domain': r['domain_name'], 'subdomain': r['subdomain'], 'definition': r['definition']}
    inverse_actions[serialize(r['domain_name'].upper(), r['name'])] = r['id']
    domains_to_actions[r['domain_name']].append(r['id'])
    domain_counts[r['domain_name']] += 1

# Only include half of the actions for each of the domains
for domain, count in domain_counts.items():
    indices = random.sample(range(count), count // 2)
    domains_to_actions[domain] = [domains_to_actions[domain][idx] for idx in indices]

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
clips: dict[str, dict] = {}
actions_to_clips: dict[int, list[int]] = defaultdict(list)
for r in res:
    clips[r['uuid']] = {'url': r['url'], 'action_id': r['action_id']}
    actions_to_clips[r['action_id']].append(r['uuid'])
    
# Initialize new DB
if os.path.isfile(edb):
    print('Database already exists at human_eval.db -- we will not overwrite it. Exiting.')
    exit(1)
schema = """
PRAGMA foreign_keys = ON;

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    subdomain TEXT,
    definition TEXT NOT NULL,
    in_context1 TEXT,
    in_context2 TEXT,
    in_context3 TEXT,
    UNIQUE (name, domain)
);

CREATE TABLE Questions(
    id INTEGER PRIMARY KEY,
    assigned INTEGER DEFAULT 0,
    finished INTEGER DEFAULT 0,
    action_id INTEGER REFERENCES Actions(id) NOT NULL,
    ground_truth INTEGER NOT NULL,
    video_url TEXT NOT NULL,
    neg_id INTEGER REFERENCES Actions(id)
);

CREATE TABLE Assignments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE,
    completed INTEGER DEFAULT 0,
    question_id INTEGER REFERENCES Question(id),
    action_id INTEGER REFERENCES Actions(id),
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    classification INTEGER,
    accurate INTEGER
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT,
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL
);
"""
econn = sqlite3.connect(edb)
for statement in schema.split(";"):
    if statement.strip():
        econn.execute(statement)
econn.commit()
econn.close()

# Pair actions with clips
action_tuples = []
question_tuples = []
for aid in actions.keys():
    relevant_clips = actions_to_clips[aid]
    if len(relevant_clips) < 5:
        print(f"Skipping over action '{actions[aid]['name']}' (id: {aid}) since it only has {len(relevant_clips)} clips.")
        continue
    
    action_tuples.append((
        aid,
        actions[aid]['name'], 
        actions[aid]['domain'], 
        actions[aid]['subdomain'],
        actions[aid]['definition'],
        clips[relevant_clips[0]]['url'],
        clips[relevant_clips[1]]['url'],
        clips[relevant_clips[2]]['url'],
    ))
    
    question_tuples.append((
        aid,
        1,
        clips[relevant_clips[3]]['url'],
        None
    ))
    
    neg_id = negatives[aid][0]
    question_tuples.append((
        aid,
        0,
        clips[actions_to_clips[neg_id][0]]['url'],
        neg_id
    ))

# Update new human eval DB
econn = sqlite3.connect(edb)
ecursor = econn.executemany('INSERT INTO Actions(id, name, domain, subdomain, definition, in_context1, in_context2, in_context3) \
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)', action_tuples)
if ecursor.rowcount != len(action_tuples):
    econn.rollback()
    raise Exception(f"Tried to add {len(action_tuples)} actions to DB, but was only able to add {ecursor.rowcount} of them.")

ecursor = econn.executemany('INSERT INTO Questions(action_id, ground_truth, video_url, neg_id) \
                            VALUES (?,?,?,?)', question_tuples)
if ecursor.rowcount != len(question_tuples):
    econn.rollback()
    raise Exception(F"Tried to add {len(question_tuples)} questions to DB, but was only able to add {ecursor.rowcount} of them.")

econn.commit()
econn.close()