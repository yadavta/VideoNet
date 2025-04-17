"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
from sqlite3 import Connection

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    """
    Executes query and returns relevant rows in a list. Does not close `conn`.
    """
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    return rows if not one else (rows[0] if rows else None)

def get_action(conn: Connection, user_id: str, study_id: str, session_id: str, load: int) -> tuple[int, str, str, str] | str:
    """
    1. If no existing assignment, assign action and return it to user
    2. If assigment exists but has not been completed, return existing action to user
    3. If assignment exists and has already been completed, return an error

    Upon case 1 or 2, returns 4-tuple of action id, action name, domain name, subdomain.
    Upon case 3, returns string.
    """
    res = conn.execute('SELECT * FROM Actions WHERE user_id = ? AND study_id = ? AND session_id = ?', (user_id, study_id, session_id)).fetchall()

    if not res:
        # CASE 1
        error = 'An error occured while trying to assign you a task. Please reload this page and try again. If the issue persists, something is wrong on our end.'
        try:
            # find available task from DB
            conn.execute('BEGIN EXCLUSIVE TRANSACTION;')
            action = conn.execute('SELECT id, name, domain_name, subdomain FROM Actions WHERE assigned = 0 AND load = ? ORDER BY RANDOM() LIMIT 1;', 
                                  (load,)).fetchall()
            if not action: 
                conn.execute('ROLLBACK;')
                return '<h1 style="text-align:center; margin-top:2rem;"> Apologies, we have no tasks remaining.</h1>'

            # attempt to assign it
            a = action[0]
            cursor = conn.execute("UPDATE Actions SET assigned = 1, assigned_at = datetime('now'), user_id = ?, study_id = ?, session_id = ? WHERE id = ? AND assigned = 0", (user_id, study_id, session_id, a['id']))
            if cursor.rowcount == 1:
                conn.execute('COMMIT')
                return a['id'], a['name'], a['domain_name'], a['subdomain']
            else:
                conn.execute('ROLLBACK')
                return error
        except Exception as e:
            conn.execute('ROLLBACK')
            print(e)
            return error
    elif int(res[0]['finished']) == 0:
        # CASE 2
        r = res[0]
        return int(r['id']), r['name'], r['domain_name'], r['subdomain']
    else:
        # CASE 3
        return 'You have already completed this Prolific task.'
    
def get_clips(conn: Connection, action_id: str) -> tuple[list[dict], list[dict]] | str:
    """
    Attempts to retrieve the clips for the specified action. 
    Upon failure, returns an error message in string form. 
    Upon success, returns two lists: one of well-trimmed clips, and one of poorly-trimmed clips. Each of those lists contains a dictionary, with one dictionary per clip.
    The dicts for well-trimmed clips have the following keys: `uuid`, `exact_url`, `og_start`, `og_end`.
    The dicts for poorly-trimmed clips have the following keys: `uuid`, `cushion_url`, `cushion_start`, `cushion_end`, `og_start`, `og_end`.
    """
    clips = query_db(conn, 'SELECT * FROM Clips WHERE action_id = ?', (action_id,))
    if not clips:
        return "An error occured while trying to fetch the clips associated with the action you were assigned. Please reload this page and try again. If the issue persists, please return the survey as something is wrong on our end."
    good_clips, bad_clips = [], []
    for c in clips:
        rating = c['rating']
        if rating == 1:
            good_clips.append({'uuid': c['uuid'], 'exact_url': c['exact_url'], 'og_start': c['og_start'], 'og_end': c['og_end']})
        elif rating == 2:
            bad_clips.append({'uuid': c['uuid'], 'cushion_url': c['cushion_url'], 'cushion_start': c['cushion_start'], 'cushion_end': c['cushion_end'], 'og_start': c['og_start'], 'og_end': c['og_end']})
    
    if not good_clips and not bad_clips:
        return "Sorry, we don't have any clips for this action. Please return the survey and message us that this error occured. We apologize for the inconvenience."
    return good_clips, bad_clips

def add_trimmings(conn: Connection, trims: list[tuple[str, float, float, int]]) -> int:
    """
    Receives a list of trimmings denoted as 4 tuples with the uuid, user-designated start time, user-designated end time, and if action name appears on-screen.
    Updates Clips table to reflect these trimmings. 
    Returns 0 on success, 1 on failure.
    """
    try:
        cursor = conn.execute('BEGIN IMMEDIATE TRANSACTION;')
        for t in trims:
            cursor.execute("UPDATE Clips SET final_start = ?, final_end = ?, onscreen = ? WHERE uuid = ?", 
                           (t[1], t[2], t[3], t[0]))
            if cursor.rowcount != 1:
                raise Exception
        conn.commit()
        return 0
    except Exception as e:
        print(e)
        conn.rollback()
        return 1

def mark_finished(conn: Connection, user_id: str, action_id: int) -> int:
    """
    Updates Actions table to reflect that the specified action has been successfully processed by the specified user.
    Returns 0 on success, 1 on failure.
    """
    try:
        cursor = conn.execute('UPDATE Actions SET finished = 1 WHERE user_id = ? AND id = ?', (user_id, action_id))
        if cursor.rowcount != 1:
            raise Exception
        conn.commit()
        return 0
    except:
        conn.rollback()
        return 1
    
def add_feedback(conn: Connection, user_id: str, study_id: str, session_id: str, feedback: str) -> int:
    """
    Logs user feedback.
    Returns 0 on success, 1 on failure.
    """
    try:
        cursor = conn.execute('INSERT INTO Feedback(thoughts, user_id, study_id, session_id) VALUES (?, ?, ?, ?)', (feedback, user_id, study_id, session_id))
        if cursor.rowcount != 1:
            raise Exception
        conn.commit()
    except:
        conn.rollback()
        return 1