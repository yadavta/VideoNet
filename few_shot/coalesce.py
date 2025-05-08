import sqlite3, argparse

parser = argparse.ArgumentParser()
parser.add_argument('-m', '--master', required=True, type=str, help='Local path to master DB where entire benchmark is coalesced')
parser.add_argument('-d', '--database', required=True, type=str, help='Local path to DB whose entries will be added to the master DB')
parser.add_argument('-n', '--number', required=False, type=int, help='Action IDs from the `-d` database will be incremented by (1000 * this integer) before being inserted to the master DB. If no number is given, one is inferred from the master DB.')
args = parser.parse_args()
master, db, n = args.master, args.database, args.number

def make_dicts(cursor, row): return dict((cursor.description[idx][0].lower(), value) for idx, value in enumerate(row))
mconn, dconn = sqlite3.connect(master), sqlite3.connect(db)
mconn.row_factory, dconn.row_factory = make_dicts, make_dicts

# Ensure that the `n` we've selected would not cause an overlap with existing action IDs
try:
    res = mconn.execute('SELECT id FROM Actions ORDER BY id DESC LIMIT 1').fetchone()
    if res:
        if 'id' not in res: raise Exception("Querying master DB's actions table returned no IDs.")
        max_id = res['id']
    else:
        max_id = -1
except Exception as e:
    print("ERROR: unable to retrieve maximum action ID from master database.")
    raise e

if n and 1000 * n <= max_id:
    print(f"ERROR: the specified `-n` was too low, as the master table contains an action with ID {max_id}.")
    exit(1)
nk = 1000 * (n if n else 1 + max_id // 1000)

# Get all actions from old DB and insert them into master DB
actions = []
try:
    res = dconn.execute('SELECT id, name, domain_name, subdomain, definition FROM Actions').fetchall()
    for r in res:
        actions.append((nk + int(r['id']), r['name'], r['domain_name'], r['subdomain'], r['definition']))
except Exception as e:
    print("ERROR: unable to retrieve actions from old DB.")
    raise e

try:
    mcursor = mconn.executemany('INSERT INTO Actions(id, name, domain_name, subdomain, definition) VALUES (?,?,?,?,?)', actions)
    if mcursor.rowcount != len(actions): raise Exception
except Exception as e:
    print("ERROR: unable to add actions into master DB.")
    mconn.rollback()
    raise e

# Get all clips from old DB and insert them into master DB
clips = []
try:
    res = dconn.execute('SELECT id, uuid, action_id, url, yt_id, start, end, trimmed, onscreen, rating FROM Clips').fetchall()
    for r in res:
        clips.append((r['uuid'], nk + int(r['action_id']), r['url'], r['yt_id'], r['start'], r['end'], r['trimmed'], r['onscreen'], r['rating']))
except Exception as e:
    print("ERROR: unable to retrieve clips from old DB.")
    raise e

try:
    mcursor = mconn.executemany('INSERT INTO Clips(uuid, action_id, url, yt_id, start, end, trimmed, onscreen, rating) \
                                VALUES (?,?,?,?,?,?,?,?,?)', clips)
    if mcursor.rowcount != len(clips): 
        raise Exception
except Exception as e:
    print("ERROR: unable to add clips into master DB.")
    mconn.rollback()
    raise e
    
# Finalize changes and clean up
try:
    mconn.commit()
except Exception as e:
    print("ERROR: unable to commit changes to master DB.")
    mconn.rollback()
    raise e
mconn.close()
dconn.close()
