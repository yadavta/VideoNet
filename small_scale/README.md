## Data Management

`Domains` table schema:

- `id`: primary key (unique identifier)
- `name`: most common name of domain (unique)

`Actions` table schema:

- `id`: primary key (unique identifier)
- `name`: most common name of the action
- `assigned`: boolean (stored as integer) representing if this action has been assigned to a Prolific user
- `assigned_at`: time that Prolific user was assigned this task; used for returning tasks programmatically due to timeout
- `finished`: boolean (stored as integer) representing if this action has been "finished", that is if a Prolific completion code has been given out for it
- `alt_names`: a comma-seperated string containing alternative names for the action
- `domain_name`: foreign key reference to `Domains(name)`
- `subdomain`: optional action type (e.g., for Football this might be "Penalty" to indicate to Prolific user that the action is a penalty)
- `user_id`: Prolific ID of user assigned to this action
- `study_id`: identifier for Prolific study through which this action was processed
- `session_id`: identifier for unique Prolific session through which this action was processed
- `token`: random 16-character token used to verify that Prolific submission is made by the same person who opened the task
- `definition`: LLM-generated definition of action with cues for what to look for in a video to easily recognize this action

`Clips` table schema:

- `id`: primary key (unique identifier)
- `action_id`: foreign key reference to `Actions(id)`
- `yt_id`: YouTube ID of YouTube video containing action (will likely be extracted from `url` programmatically)
- `url`: YouTube URL of YouTube video containing action
- `start`: clip start time in seconds
- `end`: clip end time in seconds

`Feedback` table schema:

- `id`: primary key (unique identifier)
- `thoughts`: the actual feedback
- `user_id`: Prolific ID of user who provided this feedback
- `study_id`: identifier for Prolific study through which this feedback was received
- `session_id`: identifier of unique Prolific sesssion through which this feedback was given
  
SQLite commands to create the tables:
```sql
PRAGMA foreign_keys = ON;

CREATE TABLE Domains(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    UNIQUE (name)
);

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    assigned INTEGER DEFAULT 0,
    assigned_at TEXT,
    finished INTEGER DEFAULT 0,
    alt_names TEXT,
    domain_name TEXT REFERENCES Domains(name) NOT NULL,
    subdomain TEXT,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT,
    token TEXT,
    definition TEXT,
    UNIQUE(user_id, study_id, session_id),
    UNIQUE(name, domain_name)
);

CREATE TABLE Clips(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES Actions(id),
    yt_id TEXT,
    url TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT NOT NULL,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);
```

To unassign all tasks for testing purposes:
```sql
UPDATE Actions SET user_id = NULL, study_id = NULL, session_id = NULL, token = NULL, finished = 0, assigned = 0, assigned_at = NULL;
```

To add all skateboarding tasks for testing purposes:
```sql
INSERT INTO Actions('name') VALUES ('Tic-tac'), ('Manual'), ('Drop In'), ('Carving'), ('Ollie'), ('Shuvit'), ('Kickflip'), ('50-50 Grind'), ('Pop Shuvit'), ('Heelflip'), ('Backside Flip'), ('Backside Heelflip'), ('Frontside Flip'), ('Frontside Heelflip'), ('360 Flip'), ('Laser Flip'), ('Hardflip'), ('Inward Heelflip'), ('Boardslide'), ('Noseslide'), ('Tailslide'), ('Bluntslide'), ('5-0 Grind'), ('Cooked Grind'), ('Nosegrind'), ('Smith Grind'), ('Feeble Grind'), ('Rock to Fakie'), ('Tail Stall'), ('Axle Stall'), ('Rock and Roll'), ('Nose Stall'), ('Disaster'), ('FS Smith'), ('Fakie'), ('360 Shuvit'), ('540 Flip'), ('Ghetto Bird'), ('Fakie Big Flip'), ('Front Side 180'), ('Backside 180'), ('Nose Manual'), ('No Comply 180'), ('Doubleflip'), ('Double Kickflip'), ('Impossible'), ('FS Shuvit'), ('Acid Drop'), ('Boneless'), ('Nollie'), ('Lip Slide')
```

While post-processing, make sure to check that no actions' clips were added twice (by accident) to the Clips database.
```sql
SELECT a.id, a.name AS action_name, a.domain_name, COUNT(c.id) AS clip_count
FROM Actions a JOIN Clips c ON a.id = c.action_id 
GROUP BY a.id, a.name, a.domain_name HAVING COUNT(c.id) > 7 ORDER BY clip_count DESC;
```