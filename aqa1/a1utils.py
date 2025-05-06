"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
import time
from sqlite3 import Connection

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    """
    Executes query and returns relevant rows in a list. Does not close `conn`.
    """
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    return rows if not one else (rows[0] if rows else None)

def get_assignment(conn: Connection, user_id: str, study_id: str, session_id: str) -> tuple[str, str] | str:
    """
    1. If no existing assignment, assign a batch to user and return info to user
    2. If assigment exists but has not been completed, return existing batch to user
    3. If assignment exists and has already been completed, return an error

    Upon case 1 or 2, returns 2-tuple of batch uuid and domain.
    Upon case 3, returns string.
    """
    res = conn.execute('SELECT * FROM Batches WHERE user_id = ? AND study_id = ? AND session_id = ?', (user_id, study_id, session_id)).fetchall()

    if not res:
        # CASE 1
        error = 'An error occured while trying to assign you a task. <b>Please reload this page and try again</b>. If the issue persists, something is wrong on our end.'
        try:
            # find available task from DB
            conn.execute('BEGIN EXCLUSIVE TRANSACTION;')
            batch = conn.execute('SELECT uuid, domain FROM Batches WHERE assigned = 0 ORDER BY RANDOM() LIMIT 1;').fetchall()
            if not batch:
                conn.rollback()
                return '<h1 style="text-align:center; margin-top:2rem;"> Apologies, we have no tasks remaining.</h1>'

            # attempt to assign it
            b = batch[0]
            cursor = conn.execute("UPDATE Batches SET assigned = 1, assigned_at = datetime('now'), user_id = ?, study_id = ?, session_id = ? WHERE uuid = ? AND assigned = 0", 
                                  (user_id, study_id, session_id, b['uuid']))
            if cursor.rowcount == 1:
                conn.commit()
                return b['uuid'], b['domain']
            else:
                conn.rollback()
                return error
        except Exception as e:
            conn.rollback()
            print(e)
            return error
    elif int(res[0]['finished']) == 0:
        # CASE 2
        r = res[0]
        return r['uuid'], r['domain']
    else:
        # CASE 3
        return 'You have already completed this Prolific task.'

def get_videos(c: Connection, batch_uuid: str) -> list[tuple[str, str, int, int, str]] | str:
    """
    Attempts to retrieve the videos for the specified batch. Upon failure, returns an error message in string form. Upon success, returns a list of videos, where each video is represented as a 5-tuple.
    The 5-tuple contains, in order, the UUID of the video in the Videos table, the YouTube ID of the video, the start time (in seconds) of the LLM-identified segment, and the end time (in seconds) of the LLM-identified segment, and the action name.
    """
    res = query_db(c, 'SELECT uuid, yt_id, start, end, action FROM Videos WHERE batch_uuid = ? ORDER BY yt_id', (batch_uuid,))
    if not res:
       return "An error occured while trying to fetch the videos associated with the action you were assigned. Please reload this page and try again. If the issue persists, please return the survey as something is wrong on our end." 
    return [(v['uuid'], v['yt_id'], v['start'], v['end'], v['action']) for v in res]

def convert_time_to_str(timestamp: float, end=False) -> str:
    ts = int(timestamp + 1) if end else int(timestamp)
    minutes, seconds = ts // 60, ts % 60
    if minutes:
        return f"{minutes}:{seconds:02d}"
    else:
        return f"{seconds} seconds"
    
def update_videos(conn: Connection, annotations: list[tuple[int, int, str, str, str]]) -> int:
    """
    Returns 0 on success and 1 on failure.
    """
    i = 0
    while i < 5:
        try:
            with conn:
                conn.executemany('UPDATE Videos SET correct = ?, wrong = ?, action = ? \
                                 WHERE uuid = ? AND batch_uuid = ?', annotations)
                return 0
        except Exception:
            time.sleep(0.2)
            i += 1
    return 1
        
def mark_finished(conn: Connection, batch_uuid: str, user_id: str, study_id: str, session_id: str) -> int:
    """
    Returns 0 on success and 1 on failure.
    """
    i = 0
    while i < 5:
        try:
            conn.execute('BEGIN TRANSACTION')
            cursor = conn.execute('UPDATE Batches SET finished = 1 WHERE uuid = ? AND user_id = ? AND study_id = ? AND session_id = ?',
                                  (batch_uuid, user_id, study_id, session_id))
            if cursor.rowcount != 1: raise Exception
            conn.commit()
            return 0
        except Exception:
            conn.rollback()
            time.sleep(0.2)
            i += 1
            
def add_feedback(conn: Connection, feedback: str, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Logs user feedback.

    Returns boolean indicating if operation was successful.
    """
    i = 0
    while i < 3:
        try:
            conn.execute('BEGIN TRANSACTION')
            cursor = conn.execute('INSERT INTO Feedback(thoughts, user_id, study_id, session_id) VALUES (?, ?, ?, ?)', (feedback, user_id, study_id, session_id))
            if cursor.rowcount == 1:
                conn.commit()
                return True
            else:
                raise Exception
        except Exception:
            conn.rollback()
            time.sleep(0.1)
            i += 1
    return False