"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
from sqlite3 import Connection

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    """
    DOES NOT CLOSE `conn`. THAT IS RESPONSIBILITY OF THE CALLER.
    """
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    return rows if not one else (rows[0] if rows else None)

def assign_video(conn: Connection, video_id: int, user_id: str) -> int:
    """
    Finds row in Videos table whose primary key equals `video_id` and changes its status to 4 (to reflect that it has been assigned to a Prolific user).
    Returns 0 on success, 1 on failure.

    DOES NOT CLOSE `conn`. THAT IS RESPONSIBILITY OF THE CALLER.
    """
    cursor = conn.execute('UPDATE Videos SET status = 4 WHERE id = ?', (str(video_id),))
    failure = int(cursor.rowcount != 1)
    cursor = conn.execute('UPDATE Videos SET user_id = ? WHERE id = ?', (user_id, str(video_id),))
    failure = failure or int(cursor.rowcount != 1)
    cursor = conn.execute('UPDATE UnverifiedClips SET user_id = ? WHERE video_id = ?', (user_id, str(video_id),))
    # failure = failure or int(cursor.rowcount == 0)
    conn.commit()
    return failure

def assign_videos(c: Connection, user_id: str) -> tuple[list[int] | str, int]:
    """
    Chooses a subset of available videos (i.e., videos that have unverified clips to process) to assign to a Prolific user.

    Returns 2-tuple:
        0. subset as a list of video_ids (as integers). If there are no available videos, returns string of HTML informing Prolific user of such.
        1. total number of unverified clips associated with assigned videos. If there are no available videos, returns 0.
    """
    available_videos: list[dict] | None = query_db(c, 'SELECT V.id, V.uclips_count FROM Videos as V WHERE V.status = 3 ORDER BY RANDOM() LIMIT 30;')
    if available_videos is None or len(available_videos) == 0:
        return '<h1> Error </h1> <p> Oops, we have no more tasks left. We apologize for the inconvenience.</p>', 0

    if assign_video(c, available_videos[0]['id'], user_id):
        return "<h1> Error </h1> <p> An unexpected issue occured on our end. We apologize for the inconvenience.", 0
    assigned: list[str] = [available_videos[0]['id']]
    i, total = 0, available_videos[0]['uclips_count']

    while True:
        i += 1
        if i >= len(available_videos) or len(assigned) > 10 or total > 50:
            break
        if total + available_videos[i]['uclips_count'] > 60:
            continue
        
        video_id = available_videos[i]['id']
        if assign_video(c, video_id, user_id):
            continue
        assigned.append(video_id)
        total += available_videos[i]['uclips_count']

    return assigned, total

def get_next_video_id(c: Connection, user_id: str) -> int | str:
    """
    Returns (integer) id of row in Videos table of video that the specified Prolific user should process next.
    If there are no videos assigned to the specified Prolific user, returns a string error message.
    """
    video: dict | None = query_db(c, "SELECT id, uclips_count FROM Videos WHERE user_id = ? AND status = 4 ORDER BY id LIMIT 1;", (user_id,), one=True)
    return video['id'] if video else "There are no videos assigned to this Prolific user."

def get_next_clip(c: Connection, video_id: str) -> dict | str:
    clip: dict | None = query_db(c, "SELECT * FROM UnverifiedClips WHERE video_id = ? AND processed = 0 ORDER BY num LIMIT 1;", (video_id,), one=True)
    return clip if clip else "There are no remaining clips associated with this video."

def update_uclip_as_processed(conn: Connection, clip_id: int) -> int:
    """
    Updates row in UnverifiedClips with primary key `clip_id` so that its value for the 'processed' column becomes 1.
    """
    cursor = conn.execute('UPDATE UnverifiedClips SET processed = 1 WHERE id = ?;', (str(clip_id),))
    failure = int(cursor.rowcount != 1)
    conn.commit()
    return failure

def update_video_as_processed(conn: Connection, video_id: int) -> int:
    """
    Updates row in Videos with primary key `video_id` so that its 'status' is set to 5.
    """
    cursor = conn.execute('UPDATE Videos SET status = 5 WHERE id = ?;', (str(video_id),))
    failure = int(cursor.rowcount != 1)
    conn.commit()
    return failure

def remaining_videos(c: Connection, user_id: str) -> dict | str:
    """
    Returns a dictionary with fields `nv` and `nc` representing the number of videos and clips remaining (respectively) for this Prolific user.
    If an error occurs during the underlying SQL query, an error message (in string form) is returned.

    If there are no videos left for this user, `nv` will be 0, and `nc` will be 0 or NULL.
    """
    remaining: dict | None = query_db(c, 'SELECT COUNT(*) as nv, SUM(uclips_count) as nc FROM Videos WHERE status = 4 AND user_id = ?;',
                                       (user_id,), one=True)
    if not remaining:
        return 'An error occured while fetching statistics on the number of remaining videos & clips assigned to this Prolific user.'
    return remaining

def get_exact_url(c: Connection, clip_id: str) -> str | None:
    """
    Returns value in 'exact_url' column of row in 'UnverifiedClips' with primary key `clip_id`.
    If no such row exists, returns None.
    """
    result: dict | None = query_db(c, 'SELECT exact_url FROM UnverifiedClips WHERE id = ?', (clip_id,), one=True)
    return result['exact_url'] if result else None

def get_cushion_url(c: Connection, clip_id: str) -> str | None:
    """
    Returns value in 'cushion_url' column of row in 'UnverifiedClips' with primary key `clip_id`.
    If no such row exists, returns None.
    """
    result: dict | None = query_db(c, 'SELECT cushion_url FROM UnverifiedClips WHERE id = ?', (clip_id,), one=True)
    return result['cushion_url'] if result else None

def get_clip_times(c: Connection, clip_id: str) -> tuple[float] | None:
    """
    For the row with primary key `clip_id`, returns 3-tuple containing values in the following columns respectively: 
    'start', 'end', 'cushion_start'. If no such row exists, returns None
    """
    result: dict | None = query_db(c, 'SELECT start, end, cushion_start FROM UnverifiedClips WHERE id = ?', (clip_id,), one=True)
    return result['start'], result['end'], result['cushion_start'] if result else None

def add_verified_clip(conn: Connection, start: float, end: float, clip_id: int, video_id: int, user_id: str, study_id: str, session_id: str) -> int:
    """
    Inserts a row into VerifiedClips with the column values denoted by the corresponding parameters (that is, the value for `start` goes into the 'start' column, etc).

    Returns 0 on success, 1 on failure.
    """
    # determine the 1-index number of this clip (i.e., is it the first clip extracted from the corresponding unverified clip, the sceond, the third, etc)
    cursor = conn.execute('SELECT COUNT(*) as cnt FROM VerifiedClips WHERE video_id = ?', (video_id,))
    rows = cursor.fetchall()
    num = 0 if not rows else rows[0]['cnt']
    num += 1

    # insert user-identified clip into VerifiedClips
    cursor = conn.execute('INSERT INTO VerifiedClips (start, end, num, uclip_id, video_id, user_id, study_id, session_id) VALUES (?,?,?,?,?,?,?,?)', 
                (start, end, num, clip_id, video_id, user_id, study_id, session_id))
    failure = int(cursor.rowcount == 0)
    conn.commit()
    return failure