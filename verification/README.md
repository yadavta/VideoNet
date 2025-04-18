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
- `definition`: action definition; provided to help Prolific users understand what this action entails

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
    definition TEXT,
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

## Data Analysis

Assuming >=2 1s --> "good" clip, >=2 2s --> "mediocre" clip, >=2 3s --> "bad" clip, and remaining clips are TBD, then:
- To determine how many clips have zero "good" clips
  - ```SELECT COUNT(DISTINCT a.id) FROM Actions a WHERE NOT EXISTS ( SELECT 1 FROM Clips c WHERE c.action_id = a.id AND ( SELECT COUNT(*) FROM Annotations an WHERE an.clip_id = c.id AND an.classification = 1) >= 2);```
- To determine how many clips have zero "mediocre" clips
  - ```SELECT a.* FROM Actions a WHERE NOT EXISTS ( SELECT 1 FROM Clips c WHERE c.action_id = a.id AND ( SELECT COUNT(*) FROM Annotations an WHERE an.clip_id = c.id AND an.classification = 2) >= 2);```

To get the number of 1s, 2s, and 3s each clip received:
```sql
SELECT c.id AS clip_id, SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) AS num_1, SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) AS num_2, SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) AS num_3 FROM Clips c LEFT JOIN Annotations a ON c.id = a.clip_id GROUP BY c.id, c.gcp_url, c.yt_id, c.start, c.end ORDER BY c.id;
```

Use the folloqing query to get a breakdown of how many clips fell into which distribution of votes.
```sql
SELECT votes, COUNT(*) AS num_clips FROM (SELECT c.id, CASE WHEN COUNT(DISTINCT a.classification) = 1 AND MAX(a.classification) = 1 THEN 'All 1s' WHEN COUNT(DISTINCT a.classification) = 1 AND MAX(a.classification) = 2 THEN 'All 2s' WHEN COUNT(DISTINCT a.classification) = 1 AND MAX(a.classification) = 3 THEN 'All 3s' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) = 1 AND SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) = 1 AND SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) = 1 THEN '123' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) = 1 AND SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) = 2 THEN '122' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) = 1 AND SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) = 2 THEN '133' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) = 2 AND SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) = 1 THEN '112' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 1 THEN 1 ELSE 0 END) = 2 AND SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) = 1 THEN '113' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) = 2 AND SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) = 1 THEN '223' WHEN COUNT(a.id) = 3 AND SUM(CASE WHEN a.classification = 3 THEN 1 ELSE 0 END) = 2 AND SUM(CASE WHEN a.classification = 2 THEN 1 ELSE 0 END) = 1 THEN '332' ELSE 'No Votes' END AS votes FROM Clips c LEFT JOIN Annotations a ON c.id = a.clip_id GROUP BY c.id) GROUP BY votes ORDER BY votes;
```

These are the possible (unordered) combinations of votes that the above query checks for.

- 111
- 222
- 333
- 123
- 112
- 113
- 122
- 133
- 223
- 233

To get a list of clips that have no "1" votes.
```sql
SELECT c.* FROM Clips c WHERE NOT EXISTS (SELECT 1 FROM Annotations a WHERE a.clip_id = c.id AND a.classification = 1);
```

To get a list of actions that have no clips with at least one "1" vote.
```sql
SELECT a.* FROM Actions a WHERE NOT EXISTS ( SELECT 1 FROM Clips c JOIN Annotations an ON c.id = an.clip_id WHERE c.action_id = a.id AND an.classification = 1);
```

To get all clips that have one 1, one 2, and one 3 vote for manual review.
```sql
SELECT c.id, c.gcp_url, a.name AS action_name
FROM Clips c 
JOIN Actions a ON c.action_id = a.id 
JOIN Annotations an ON c.id = an.clip_id
GROUP BY c.id 
HAVING SUM(an.classification = 1) = 1 AND SUM(an.classification = 2) = 1 AND SUM(an.classification = 3) = 1;
```