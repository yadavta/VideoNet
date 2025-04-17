# Clip Trimming

Given a list of 7 clips collected by Prolific User A (via `small_scale`), k of which are well-trimmed and 7-k of which are poorly trimmed (as determined by Prolific User B via `verification`), have Prolific User C fix the trimmings for the 7-k poorly trimmed clips.

## Data Management

**WARNING: ANY UPDATES TO THIS SECTION MUST BE REFLECTED IN `../prep/init_trimming_db.py` AS WELL.**

Note that the `Actions` table is sourced directly from the previous (verification) stage. Meanwhile, the `Clips` table is a result of our preprocessing logic being applied to various tables from the previous stage (in particular, the `ratings` columns is based on the previous stage's `Annotations` table). The `Feedback` table is standard across all stages.

`Actions` table schema:
- `id`: primary key (unique identifier)
- `name`: most common name of the action
- `domain_name`: e.g., Football, Skateboarding, etc.
- `subdomain`: optional action type (e.g., for Football this might be "Penalty" to indicate to Prolific user that the action is a penalty)
- `assigned`: boolean (stored as integer) representing if this action has been assigned to a Prolific user
- `finished`: boolean (stored as integer) representing if this action has been finished by the Prolific user
- `user_id`: Prolific ID of user assigned to this action
- `study_id`: identifier for Prolific study through which this action was trimmed
- `session_id`: identifier for unique Prolific session through which this action was trimmed
- `assigned_at`: time that Prolific user was assigned this task; used for returning tasks due to timeout

`Clips` table schema:
- `id`: primary key (unique identifier)
- `action_id`: foreign key reference to `Actions(id)`
- `exact_url`: publicly-accessible URL of clip with exact trimming
- `cushion_url`: publicly-accessible URL of clip with cushion on both sides (i.e., two seconds before & after the designated start and end times of the clip)
- `uuid`: unique identifier assigned to clip that stays with it across stages
- `yt_id`: YouTube ID of YouTube video containing action
- `og_start`: where the annotator from first (collection) stage determined the clip starts
- `og_end`: where the annotator from first (collection) stage determined the clip ends
- `cushion_start`: where (w.r.t. the original video) the clip stored at `cushion_url` 
- `cushion_end`: where (w.r.t. the original vieo) the clip stored at `cushion_url` ends
- `final_start`: where the annotator from this stage thinks the clip should start; will be null if `updated` is False (0)
- `final_end`: where the annotator from this stage thinks the clip should end; will be null if `updated` is False (0)
- `votes`: three character string. All characters are integers. First character is how many "yes, and well-trimed" votes this clip got in the previous stage; second character is how many "yes, but poorly-trimmed" votes it got; third character is "no" votes.
- `rating`: 1, 2, or 3. Based on user annotations from verification stage, this is set to 1 if we believe it is a well-trimmed clip, 2 if we believe it is a poorly-trimmed clip, and 3 if we believe it is the clip of another action.
- `onscreen`: boolean (stored as integer) denoting if the action name appears as on-screen text.

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
    rating INTEGER,
    onscreen INTEGER
);

CREATE TABLE Feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thoughts TEXT NOT NULL,
    user_id TEXT,
    study_id TEXT,
    session_id TEXT
);
```

For debugging purposes, you can clear all assignments as such:
```sql
UPDATE Actions SET assigned=0, finished=0, user_id=NULL, study_id=NULL, session_id=NULL, assigned_at=NULL WHERE user_id='tantan';
UPDATE Clips SET final_start=NULL, final_end=NULL, onscreen=NULL WHERE onscreen IS NOT NULL;
```

## Data Analysis

To check for clips that the annotators all disagreed on:
```sql
SELECT c.id, a.name AS action_name, c.exact_url, c.cushion_url FROM Clips c JOIN Actions a ON c.action_id = a.id WHERE c.rating='-1';
```

To check for actions that have no well-trimmed clips:
```sql
SELECT a.* FROM Actions a WHERE NOT EXISTS (SELECT 1 FROM Clips c WHERE c.action_id = a.id AND c.rating = 1);
```

To check for actions that have no poorly-trimed clips (and also how many well-trimmed clips they have):
```sql
SELECT a.*, COUNT(CASE WHEN c.rating = 1 THEN c.id ELSE NULL END) AS num_good_clips 
FROM Actions a LEFT JOIN Clips c ON a.id = c.action_id WHERE 
NOT EXISTS (SELECT 1 FROM Clips c2 WHERE c2.action_id = a.id AND c2.rating = 2) GROUP BY a.id;
```

To mark the actions with no poorly-trimmed clips as already processed so no Prolific users are assigned it:
```sql
UPDATE Actions SET assigned = 1, finished = 1 WHERE NOT EXISTS (SELECT 1 FROM Clips c WHERE c.action_id = Actions.id AND c.rating = 2);
```