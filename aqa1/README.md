`Domains` table schema:
- `name`: primary key (unique identifier)

`Batches` table schema:
- `id`
- `uuid`
- `assigned`
- `assigned_at`: time that Prolific user was assigned this task; used for returning tasks programmatically due to timeout
- `finished`
- `user_id`
- `study_id`
- `session_id`
- `domain`
- `size`
  

`Videos` table schema:

- `id`
- `batch_uuid`
- `yt_id`: text
- `correct`: boolean (represented as integer); denotes if user thinks this clip includes instance of action being performed correctly
- `wrong`: boolean (represented as integer); denotes if user thinks this clip includes instance of action being perfromed incorrectly
- `start`: float; start time of segment in YouTube video in seconds
- `end`: float; end time of segment in YouTube video in seconds
- `action`: text; user's best guess what the action is
- `domain`: text; foreign key reference to `Domains(name)`
- `uuid`: unique identifier (unique across batches)

`Feedback` table schema:

- `id`: primary key (unique identifier)
- `thoughts`: the actual feedback
- `user_id`: Prolific ID of user who provided this feedback
- `study_id`: identifier for Prolific study through which this feedback was received
- `session_id`: identifier of unique Prolific sesssion through which this feedback was given

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE Domains(
    name TEXT PRIMARY KEY,
    UNIQUE (name)
);

CREATE TABLE Batches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE,
    assigned INTEGER DEFAULT 0,
    assigned_at TEXT,
    finished INTEGER DEFAULT 0,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT,
    domain TEXT REFERENCES Domains(name),
    size INTEGER
);

CREATE TABLE Videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_uuid TEXT REFERENCES Batches(uuid),
    yt_id TEXT NOT NULL,
    correct INTEGER DEFAULT -1,
    wrong INTEGER DEFAULT -1,
    start REAL,
    end REAL,
    action TEXT,
    domain TEXT REFERENCES Domains(name),
    uuid TEXT UNIQUE
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);
```