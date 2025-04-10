# Clip Verification

Given a list of 7 clips of an action proposed by Prolific users, ask another Prolific user to verify that all 7 clips are of the same action and are well-trimmed.

## Data Management

**WARNING: ANY UPDATES TO THIS SECTION MUST BE REFLECTED IN `collection_to_verification.py` AS WELL.**

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
- `assigned_at`: timestamp of when this assignment was made

`Clips` table schema:
- `id`: primary key (unique identifier)
- `action_id`: foreign key reference to `Actions(id)`
- `gcp_url`: publicly-accessible URL of clip (likely hosted on Google Cloud)
- `uuid`: unique identifier assigned to clip that stays with it across stages
- `yt_id`: YouTube ID of YouTube video containing action
- `start`: where the annotator from previous (collection) stage determined the clip starts
- `end`:where the annotator from previous (collection) stage determined the clip ends

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

`Feedback` table schema:

- `id`: primary key (unique identifier)
- `thoughts`: the actual feedback
- `user_id`: Prolific ID of user who provided this feedback
- `study_id`: identifier for Prolific study through which this feedback was received
- `session_id`: identifier of unique Prolific sesssion through which this feedback was given

These tables can be created as follows.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE Actions(
    id INTEGER PRIMARY KEY,
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
    assigned_at TEXT NOT NULL,
    UNIQUE (action_id, user_id, study_id)
);

CREATE TABLE Clips(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id INTEGER NOT NULL REFERENCES Actions(id),
    gcp_url TEXT NOT NULL UNIQUE,
    uuid TEXT NOT NULL UNIQUE,
    yt_id TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL
);

CREATE TABLE Annotations(
    id INTEGER PRIMARY KEY,
    clip_id INTEGER REFERENCES Clips(id) NOT NULL,
    classification INTEGER DEFAULT 0,
    action_id INTEGER REFERENCES Actions(id) NOT NULL,
    user_id TEXT NOT NULL,
    study_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    UNIQUE (clip_id, user_id, study_id)
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT NOT NULL,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);
```

Add some clips for testing purposes
```sql
INSERT INTO Actions('name', 'domain_name') VALUES ('Laser Flip', 'Skateboarding'), ('Kickflip', 'Skateboarding');
INSERT INTO Clips('action_id', 'gcp_url') VALUES (1, 'https://storage.googleapis.com/action-atlas/public/laser_flip_good.mp4'), (1, 'https://storage.googleapis.com/action-atlas/public/laser_flip_3.mp4'), (1, 'https://storage.googleapis.com/action-atlas/public/laser_flip_poor.mp4'), (1, 'https://storage.googleapis.com/action-atlas/public/laser_flip_2.mp4'), (2, 'https://storage.googleapis.com/action-atlas/public/fs_flip_6.mp4');
```