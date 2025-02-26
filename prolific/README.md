## Design

Given a list of videos and their corresponding clips in a SQLite database, verifies (and adjusts, when needed) clip trimmings via non-expert human annotators on Prolific, saving updated clips to DB.

## Data Schema

The SQLite file `data.db` contains three SQL tables: a `Videos` table for the original YouTube videos, a `UnverifiedClips` table for the trimmings produced by our automated pipeline, and a `VerifiedClips` table for the trimmings certified by Prolific users.

`Videos` table schema:
  - `id`: primary key (unique identifier)
  - `domain`: domain that this video belongs to (e.g., skateboarding)
  - `action`: video is supposed to contain clips of this (e.g., front flip)
  - `yt_id`: YouTube ID for this vidoe
  - `status`: an integer between 1 and 5 (inclusive) as described below:
    - 1: the video has been added to `videos`
    - 2: the video is being processed by Gemini/Qwen
    - 3: the video has been added to `UnverifiedClips`
    - 4: the video is being processed by Prolific
    - 5: the video has been added to `VerifiedClips`
  - `user_id`: Prolific ID of user assigned to this video
  - `filename`: our copy of this YouTube video is stored in the file with this name in our bucket
  - `duration`: length of video in seconds
  - `uclips_count`: number of clips identified by Gemini/Qwen
  - `vclips_count`: number of clips verified by Prolific user


`UnverifiedClips` table schema:
  - `id`: primary key (unique identifier)
  - `video_id`: foreign key reference to `Videos(id)`
  - `user_id`: Prolific ID of user assigned to verify this clip
  - `num`: 1-indexed index of clip (chronologically) amongst all clips extracted from this video
  - `start`: clip start time in seconds
  - `end`: clip end time in seconds
  - `cushion_start`: start time of the cushioned clip (that is, clip with a few seconds of padding on each side)
  - `cushion_end`: end time of the cushioned clip
  - `exact_url`: public URL of clip with exact trimming
  - `cushion_url`: clip URL of clip with cushioned trimming (a few extra seconds on both ends)
  - `processed`: boolean (stored as integer) representing if a Prolific user has been shown this clip yet

`VerifiedClips` table schema:
  - `id`: primary key (unique identifier)
  - `uclip_id`: foreign key reference to `UnverifiedClips(id)`
  - `video_id`: foreign key reference to `Videos(id)`
  - `num`: 1-indexed index of clip (chronologically) amongst all clips verified by user from this video
  - `start`: clip start time in seconds
  - `end`: clip start time in seconds
  - `user_id`: Prolific ID of user that verified this clip
  - `study_id`: identifier for Prolific study through which this clip was verified
  - `session_id`: identifier for the unique Prolific session through which this clip was verified


These can be created in SQLite with the following commands:
```bash
PRAGMA foreign_keys = ON;

CREATE TABLE Videos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status INTEGER DEFAULT 1,
  user_id TEXT,
  domain TEXT,
  action TEXT,
  yt_id TEXT,
  filename TEXT NOT NULL,
  duration REAL,
  uclips_count INTEGER,
  vclips_count INTEGER
);

CREATE TABLE UnverifiedClips(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id INTEGER NOT NULL REFERENCES Videos(id),
  user_id TEXT,
  num INTEGER NOT NULL,
  start REAL NOT NULL,
  end REAL NOT NULL,
  cushion_start REAL,
  exact_url TEXT NOT NULL,
  cushion_url TEXT NOT NULL,
  processed INTEGER DEFAULT 0
  UNIQUE(video_id, num)
);

CREATE TABLE VerifiedClips(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uclip_id INTEGER NOT NULL REFERENCES UnverifiedClips(id),
  video_id INTEGER NOT NULL REFERENCES Videos(id),
  num INTEGER NOT NULL,
  start REAL NOT NULL,
  end REAL NOT NULL,
  user_id TEXT NOT NULL,
  study_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  UNIQUE (video_id, num)
)
```

To reset for testing purposes:
```SQL
UPDATE Videos SET status = 3,  user_id = NULL;
UPDATE UnverifiedClips SET user_id = NULL, processed = 0;
```

## User Routing

- [X] All users are routed to `start` by Prolific
- [X] On `start`, they click a button which redirects them to `dashboard` and allocates videos to them
- [X] On `dashboard`, they click a button which redirects them to `count_next` and determines a specific video for them
  - [X] if no videos exist, redirect to finish
- [X] On `count`, 
  - [X] first case on what type of clip they are counting
    - next: the next clip from their current video is fetched (if no clips exist, redirect to dashboard)
    - remaining: the existing clip is trimmed such that it starts at the old end time
  - [X] second the user determines if the clip has 0, 1, or multiple actions:
    - *note that this is implemented in `process_count`*
    - [X] 0: redirect to `count_next`
    - [X] 1: redirect to `trim`
    - [X] many: redirect to `trim` 
- [X] On `trim`, the user verifies the trimming of the clip and determines if a clip exists or not (Y/N)
  - [X] if coming via `count_next`, show cushion url; if coming via `count_remaining`, show exact url with updated end time
  - [X] Y: 
    - [X] update VerifiedClips DB to reflect new clip we found
    - [X] then, case on the number of clips the user found in past step...
      - [X] 1: redirect to `count_next`
      - [X] many: redirect to `count_remaining`
  - [X] N: redirect to `count_next`

## Acknowledgments + Dependencies
- We use [Carlos Galan Cladera](https://github.com/cladera)'s Video.js [offset plugin](https://github.com/cladera/videojs-offset) to "clip" videos on the fly when asking the user to verify their clip trimming. 
- We heavily modify [Teuyot](https://github.com/Teyuto)'s Video.js [trimmer plugin](https://github.com/Teyuto/videojs-trimmer) to provide the interface for users to trim videos.