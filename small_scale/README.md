`Actions` table schema:
    - `id`: primary key (unique identifier)
    - `name`: most common name of the action
    - `alt_names`: a comma-seperated string containing alternative names for the action
    - `status`: an integer between 1 and 3 (inclusive) representing the status of data collection for this action:
      - 1: awaiting assignment to a user
      - 2: assigned to a user, waiting on the user to finish processing it
      - 3: processed/done
    - `user_id`: Prolific ID of user assigned to this action
    - `study_id`: identifier for Prolific study through which this action was processed
    - `session_id`: identifier for unique Prolific study through which this action was processed

`Clips` table schema:
    - `id`: primary key (unique identifier)
    - `action_id`: foreign key reference to `Actions(id)`
    - `yt_id`: YouTube ID of YouTube video containing action (will likely be extracted from `url` programmatically)
    - `url`: YouTube URL of YouTube video containing action
    - `start`: clip start time in seconds
    - `end`: clip end time in seconds

`Sessions` table schema:
    - `id`: primary key (unique identifier)
    - `token`: randomly generated "token" that verifies that user actually finished survey
    - `user_id`: Prolific ID of user assigned to this action
    - `study_id`: identifier for Prolific study through which this action was processed
    - `session_id`: identifier for unique Prolific study through which this action was processed
    - `finished`: boolean (stored as integer) representing if this session has been "finished", that is if a Prolific completion code has been given out for it
  
SQLite commands to create the tables:
```sql
PRAGMA foreign_keys = ON;

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status INTEGER DEFAULT 1,
    name TEXT NOT NULL,
    alt_names TEXT,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);

CREATE TABLE Clips(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES Actions(id),
    yt_id TEXT,
    url TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL
);

CREATE TABLE Sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    finished INTEGER DEFAULT 0,
    UNIQUE(user_id, study_id, session_id)
);
```

To unassign all tasks for testing purposes:
```sql
UPDATE Actions SET status = 1, user_id = NULL, study_id = NULL, session_id = NULL;
```

To add all skateboarding tasks for testing purposes:
```sql
INSERT INTO Actions('name') VALUES ('Tic-tac'), ('Manual'), ('Drop In'), ('Carving'), ('Ollie'), ('Shuvit'), ('Kickflip'), ('50-50 Grind'), ('Pop Shuvit'), ('Heelflip'), ('Backside Flip'), ('Backside Heelflip'), ('Frontside Flip'), ('Frontside Heelflip'), ('360 Flip'), ('Laser Flip'), ('Hardflip'), ('Inward Heelflip'), ('Boardslide'), ('Noseslide'), ('Tailslide'), ('Bluntslide'), ('5-0 Grind'), ('Cooked Grind'), ('Nosegrind'), ('Smith Grind'), ('Feeble Grind'), ('Rock to Fakie'), ('Tail Stall'), ('Axle Stall'), ('Rock and Roll'), ('Nose Stall'), ('Disaster'), ('FS Smith'), ('Fakie'), ('360 Shuvit'), ('540 Flip'), ('Ghetto Bird'), ('Fakie Big Flip'), ('Front Side 180'), ('Backside 180'), ('Nose Manual'), ('No Comply 180'), ('Doubleflip'), ('Double Kickflip'), ('Impossible'), ('FS Shuvit')
```