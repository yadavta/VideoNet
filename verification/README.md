# Clip Verification

Given a list of 7 clips of an action proposed by Prolific users, ask another Prolific user to verify that all 7 clips are of the same action and are well-trimmed.

## Data Management

Note the existence of an `Assignments` table. In `small_scale`, we had a bijection between actions and tasks, so we extended our `Actions` table to serve as an assignment tracker too. In this case, we want 3-5 assignments per action, so we need a seperate table to keep track of assignments/tasks.

`Actions` table schema:
- `id`: primary key (unique identifier)
- `name`: most common name of the action
- `assigned`: integer representing how many Prolific users have been assigned to this action
- `finished`: integer representing how many Prolific users have finished this action, that is how many Prolific completion codes have been given out for this action
- `domain_name`: e.g., Football, Skateboarding, etc.
- `subdomain`: optional action type (e.g., for Football this might be "Penalty" to indicate to Prolific user that the action is a penalty)

`Assignments` table schema:
- `id`: primary key (unique identifier)
- `completed`: boolean (stored as integer) representing if a Prolific completion code has been issued for this assignment
- `action_id`: foreign key reference to `Actions(id)`
- `user_id`: Prolific ID of user who this assignment is for
- `study_id`: identifier for the Prolific study this assignment is for
- `session_id`: identifier for the unique Prolific session this assignment is for

`Clips` table schema:
- `id`: primary key (unique identifier)
- `action_id`: foreign key reference to `Actions(id)`
- `gcp_url`: publicly-accessible URL of clip (likely hosted on Google Cloud)

`Annotations` table schema:
- `id`: primary key (unique identifier)
- `clip_id`: foreign key reference to `Clips(id)`
- `classification`: integer representing what Prolific user thinks about the clip:
  - 0: N/A, not processed by user yet
  - 1: yes, this is a clip of the desired action
  - 2: yes, BUT the trimming could be improved
  - 3: no, this is NOT a clip of the desired action
- `user_id`: Prolific ID of user who provided this annotation
- `study_id`: identifier for Prolific study through which this annotation was generated
- `session_id`: identifier for unique Prolific session through which this annotation was generated

These tables can be created as follows.
```sql
PRAGMA foreign_keys = ON;

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    assigned INTEGER DEFAULT 0,
    finished INTEGER DEFAULT 0,
    subdomain TEXT,
    UNIQUE(name, domain_name)
);

CREATE TABLE Assignments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES Actions(id),
    completed INTEGER DEFAULT 0,
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    UNIQUE (action_id, user_id, study_id)
);

CREATE TABLE Clips(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES Actions(id),
    gcp_url TEXT NOT NULL UNIQUE
);

CREATE TABLE Annotations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER REFERENCES Clips(id) NOT NULL,
    classification INTEGER DEFAULT 0,
    action_id INTEGER REFERENCES Actions(id) NOT NULL,
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL
);
```