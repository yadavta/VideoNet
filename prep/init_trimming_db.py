import os, sqlite3, argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Prepares database for trimming stage.")
parser.add_argument('-n', '--name', required=True, type=str, help='e.g., skateboarding, football, etc.')
parser.add_argument('-v', '--vdb', required=True, type=str, help='local path to database from verification stage')
args = parser.parse_args()

# Initialize trimming database to barebones schema
tdb = f'trimming_{args.name.lower()}.db'
Path(tdb).touch(exist_ok=True)
schema = """PRAGMA foreign_keys = ON;

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    assigned INTEGER DEFAULT 0,
    finished INTEGER DEFAULT 0,
    subdomain TEXT,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT,
    assigned_at TEXT,
    UNIQUE (user_id, study_id, session_id),
    UNIQUE (name, domain_name)
);

CREATE TABLE Clips(
    id INTEGER PRIMARY KEY,
    action_id INTEGER NOT NULL REFERENCES Action(id),
    exact_url TEXT NOT NULL UNIQUE,
    cushion_url TEXT,
    uuid TEXT NOT NULL UNIQUE,
    yt_id TEXT NOT NULL,
    og_start REAL,
    og_end REAL,
    cushion_start REAL,
    cushion_end REAL,
    final_start REAL,
    final_end REAL,
    votes TEXT NOT NULL,
    rating INTEGER
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT NOT NULL,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);"""
tconn = sqlite3.connect(tdb)
for statement in schema.split(";"):
    if statement.strip():
        tconn.execute(statement)
tconn.commit()
tconn.close()

# Get all actions from verification db
vconn = sqlite3.connect(args.vdb)
def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
vconn.row_factory = make_dicts
actions = vconn.execute('select * from actions').fetchall()

# Add them to the trimming db
sql = "INSERT INTO Actions (id, name, domain_name, subdomain) VALUES "
for a in actions:
    subdomain = a['subdomain'] if a['subdomain'] else 'NULL'
    sql += f" {a['id'], a['name'], a['domain_name'], subdomain},"
if sql[-1] == ',': sql = sql[:-1]
print(sql)
tconn = sqlite3.connect(tdb)
tcursor = tconn.cursor()
tcursor.execute(sql)
if tcursor.rowcount == len(actions):
    tconn.commit()
else:
    print("Aborting. Unable to copy over all actions from the verification stage db.")