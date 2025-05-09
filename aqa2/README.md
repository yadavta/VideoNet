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
- `correct_start`: float (seconds); start time for 
- `correct_end`: float (seconds); end time for 
- `wrong_start`: float (seconds); start time for
- `wrong_end`: float (second); end time for
- `pos_rsn`: LLM-generated explanation of what is correct about the action
- `neg_rsn`: LLM-generated explanation of what is wrong about the action
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
    correct_start INT,
    correct_end INT,
    wrong_start INT,
    wrong_end INT,
    pos_rsn TEXT NOT NULL,
    neg_rsn TEXT NOT NULL,
    start REAL,
    end REAL,
    action TEXT NOT NULL,
    domain TEXT REFERENCES Domains(name) NOT NULL,
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