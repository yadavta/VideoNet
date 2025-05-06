import argparse, os, sqlite3, uuid
import pandas as pd

BATCH_SIZE = 5

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--pandasfile', type=str, required=True, help='local path to parquet file from reza')
parser.add_argument('-d', '--database', type=str, required=True, help='local path to sqlite3 db for web server')
args = parser.parse_args()
pfile, db = args.pandasfile, args.database
if not os.path.isfile(pfile):
    raise Exception(f'could not locate the Parquet at {pfile}')
if not os.path.isfile(db):
    raise Exception(f'please initialize a DB at {db} with the correct schema')

conn = sqlite3.connect(db)
def make_dicts(cursor, row): return dict((cursor.description[idx][0].lower(), value) for idx, value in enumerate(row))
conn.row_factory = make_dicts

data = pd.read_parquet(pfile)
records = data.to_dict(orient="records")

# Get domains add to DB
domains = set()
for rec in records:
    domains.add(rec['domain'].strip().lower())
print("Domains Found: ", domains, '\n')
confirm_domains = input("Enter 'yes' (without quotations) to confirm that these domain names look correct. ")
print('\n')
if confirm_domains != 'yes':
    exit(1)
cursor = conn.executemany('INSERT INTO Domains(name) VALUES (?)', [(d,) for d in domains])
if cursor.rowcount != len(domains):
    conn.rollback()
    print('oops')
else:
    conn.commit()
    print('\tdomains added!')

# Get videos add to DB
to_add = []
for rec in records:
    to_add.append((rec['yt_id'].strip(), rec['start'], rec['end'], rec['domain'].strip().lower(), rec['response']['action'], 
                   str(uuid.uuid4()), rec['response']['correct'], rec['response']['wrong']))
conn.execute('BEGIN TRANSACTION;')
cursor = conn.executemany("INSERT INTO Videos(yt_id, start, end, domain, action, uuid, pos_rsn, neg_rsn) VALUES(?,?,?,?,?,?,?,?)", to_add)
if cursor.rowcount != len(to_add):
    conn.rollback()
    print('uh oh')
else:
    conn.commit()
    print('\tvideos added :)')
    
# Determine batches and add to DB
rows = conn.execute('SELECT id, uuid, domain FROM Videos ORDER BY domain').fetchall()
if len(rows) != len(to_add):
    print("# of videos in DB is not equal to # of videos we just added")
    exit(1)

batches = []
curr_domain: str = ""
curr_batch: list[str] = []
for row in rows:
    if len(curr_batch) == BATCH_SIZE or curr_domain != row["domain"]:
        # save the current batch
        curr_batch.insert(0, curr_domain)
        batches.append(curr_batch)
        
        # start new batch
        curr_domain = row["domain"]
        curr_batch = []
        curr_batch.append(row["uuid"])
    else:
        curr_batch.append(row["uuid"])

del batches[0] # fix fencepost

for batch in batches:
    domain = batch[0]
    unique = str(uuid.uuid4())
    cursor = conn.execute("INSERT INTO Batches(domain, uuid, size) VALUES (?, ?, ?)", (domain, unique, len(batch) - 1))
    if cursor.rowcount != 1:
        conn.rollback()
        raise Exception(f"unable to insert batch for domain {domain}")
    cursor = conn.executemany("UPDATE Videos SET batch_uuid = ? WHERE uuid = ?", ([(unique, batch[i]) for i in range(1, len(batch))]))
    if cursor.rowcount != len(batch) - 1:
        conn.rollback()
        raise Exception(f"batch had {len(batches) - 1} videos but only {cursor.rowcount} of them could be updated")

conn.commit()
print("\tbatches generated!\n")