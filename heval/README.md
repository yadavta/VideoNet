`Actions` table schema:
- `id`: primary key (unique identifier)
- `name`
- `domain`
- `subdomain`
- `definition`
- `in_context1`
- `in_context2`
- `in_context3`

`Questions` table schema:
- `id`: primary key (unique identifier)
- `assigned`: integer (NOT boolean; will range from 0 to 3)
- `finished`: integer (NOT boolean; will range from 0 to 3)
- `action_id`: foreign key reference to `Actions(id)`
- `ground_truth`: boolean (stored as integer); True indicates the solution is 'yes', False indicates the solution is 'no'
- `video_url`: public URL to video that question concerns

`Assignments` table schema:
- `id`: primary key (unique identifier)
- `uuid`
- `completed`: boolean (stored as integer)
- `question_id`: foreign key reference to `Questions(id)`
- `user_id`
- `study_id`
- `session_id`
- `assigned_at`
- `classification`: boolean (stored as integer); True indicates user responded 'yes', False indicates user responded 'no'
- `accurate`: boolean (sotred as integer); True iff `classification` equals `ground_truth` field in corresponding `Questions` table entry

`Feedback` table schema:
- `id`: primary key (unique identifier)
- `thoughts`
- `user_id`
- `study_id`
- `session_id`

These tables can be created as follows.

**ANY CHANGES TO THIS FILE MUST BE REFLECTED IN `/few_shot/prep_human.py`**.

```sql
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
```