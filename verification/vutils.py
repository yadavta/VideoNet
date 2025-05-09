"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
from sqlite3 import Connection

NUM_ANNOTATORS_PER_CLIP = 3     # how many workers should verify each clip?

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    return rows if not one else (rows[0] if rows else None)

def has_unassigned_tasks(c: Connection) -> bool | str:
    """
    Returns True if Actions table has at least one row with a value of 1 in the 'assigned' column. Otherwise returns False.

    If an issue occurs while executing the SQL query, a string error message is returned instead.
    """
    result: dict[str, int] | None = query_db(c, f'SELECT COUNT(*) as cnt FROM Actions WHERE assigned < {NUM_ANNOTATORS_PER_CLIP}', one=True)
    if not result:
        return 'An error occured while trying to check if we have any tasks left for you to do.'
    return result['cnt'] > 0

def get_action(conn: Connection, user_id: str, study_id: str, session_id: str) -> tuple[int, str, str, str | None, str | None] | str:
    """
    1. If no existing assignment, assign action and return it to user
    2. If assigment exists but has not been completed, return existing action to user
    3. If assignment exists and has already been completed, return an error

    Upon case 1 or 2, returns 5-tuple of action id, action name, domain name, subdomain, definition.
    Upon case 3, returns string.
    """
    res = conn.execute('SELECT * FROM Assignments WHERE user_id = ? AND study_id = ? AND session_id = ?', (user_id, study_id, session_id)).fetchall()

    if not res:
        # CASE 1
        error = 'An error occured while trying to assign you a task. Please reload this page and try again. If the issue persists, something is wrong on our end.'
        try:
            # find 10 available tasks from DB
            matched = False
            conn.execute('BEGIN EXCLUSIVE TRANSACTION;')
            actions = conn.execute('SELECT id, name, domain_name, subdomain, assigned, definition FROM Actions WHERE assigned < ? ORDER BY RANDOM() LIMIT 10;', (NUM_ANNOTATORS_PER_CLIP,)).fetchall()
            if not actions: 
                conn.rollback()
                return error
            
            # see if any of these 10 tasks work with our user (i.e., check for overlap)
            for a in actions:
                overlap = conn.execute('SELECT * FROM Assignments WHERE action_id = ? AND user_id = ?', (a['id'], user_id)).fetchall()
                if not overlap:
                    action_id, action_name, domain_name, subdomain, curr_assigned, defn = a['id'], a['name'], a['domain_name'], a['subdomain'], a['assigned'], a['definition']
                    matched = True
                    break
            
            # could not find an available task
            if not matched:
                return 'We have run out of tasks for you. Apologies.'

            # found an available task; attempt to assign it
            cursor1 = conn.execute('UPDATE Actions SET assigned = ? WHERE id = ?', (int(curr_assigned) + 1, action_id))
            cursor2 = conn.execute("INSERT INTO Assignments(action_id, user_id, study_id, session_id, assigned_at) VALUES (?, ?, ?, ?, datetime('now'))", 
                                   (action_id, user_id, study_id, session_id))
            if cursor1.rowcount == 1 and cursor2.rowcount == 1:
                conn.commit()
                return action_id, action_name, domain_name, subdomain, defn
                
            # unable to assign the task; rollback changes and return error
            conn.rollback()
            return error
        except Exception as e:
            conn.rollback()
            return error
    elif int(res[0]['completed']) == 0:
        action_id = res[0]['action_id']
        res = conn.execute('SELECT * FROM Actions WHERE id = ?', (action_id,)).fetchall()
        if not res:
            return 'An error occured while resuming your task.'
        return int(res[0]['id']), res[0]['name'], res[0]['domain_name'], res[0]['subdomain'], res[0]['definition']
    else:
        # CASE 3
        return 'You have already completed this Prolific task.'
    
def get_clips(c: Connection, action_id: str) -> list[tuple[int, str]] | str:
    """
    Attempts to retrieve the clips for the specified action. Upon failure, returns an error message in string form. Upon success, returns a list of clips, where each clip is represented as a 2-tuple.
    The 2-tuple contains, in order, the (integer) primary key of the clip in the Clips table, and a publicly-accessible URL of the clip (likely hosted on GCP) in strong form.
    """
    res = query_db(c, 'SELECT id, gcp_url AS url FROM Clips WHERE action_id = ?', (action_id,))
    if not res:
       return "An error occured while trying to fetch the clips associated with the action you were assigned. Please reload this page and try again. If the issue persists, please return the survey as something is wrong on our end." 
    return [(c['id'], c['url']) for c in res]

def add_annotations(conn: Connection, clips: list[tuple[int, int]], action_id: str, user_id: str, study_id: str, session_id: str) -> int:
    """
    For each entry in `clips`, adds a row in the Annotations table to reflect that the Prolific submission uniquely identified by the provdied `user_id`, `study_id`, and `session_id`
    determined that the clip with primary key `clips[0]` in Clips for the action in Actions with primary key `action_id` should be classified as `clips[1]`.

    Returns 0 on success, 1 on failure, and -1 if annotations have been added already.
    """
    conn.execute('BEGIN TRANSACTION;')
    for clip in clips:
        try:
            cursor = conn.execute('INSERT INTO Annotations(clip_id, classification, action_id, user_id, study_id, session_id) VALUES(?, ?, ?, ?, ?, ?)',
                           (clip[0], clip[1], action_id, user_id, study_id, session_id))
            if cursor.rowcount != 1:
                conn.execute('ROLLBACK;')
                return 1
        except Exception:
            conn.execute('ROLLBACK;')
            return -1
    conn.execute('COMMIT;')
    return 0

def mark_finished(conn: Connection, user_id: str, action_id: str) -> int:
    """
    Increments the `finished` counter for the specified action by specified user. Returns 0 on success, 1 on failure.
    
    Assumes that this is only (successfully) called once per assigment.
    """
    conn.execute('BEGIN EXCLUSIVE TRANSACTION;')
    res = conn.execute('SELECT finished FROM Actions WHERE id = ?', (action_id,)).fetchall()
    if len(res) != 1 :
        conn.execute('ROLLBACK;')
        return 1
    curr_finished = res[0]['finished']
    cursor1 = conn.execute('UPDATE Actions SET finished = ? WHERE id = ? ', (curr_finished + 1, action_id))
    cursor2 = conn.execute('UPDATE Assignments SET completed = 1 WHERE user_id = ? AND action_id = ?', (user_id, action_id))
    if cursor1.rowcount != 1 or cursor2.rowcount != 1:
        conn.execute('ROLLBACK;')
        return 1
    conn.execute('COMMIT;')
    return 0

def add_feedback(conn: Connection, feedback: str, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Logs user feedback.

    Returns boolean indicating if operation was successful.
    """
    try:
        cursor = conn.execute('INSERT INTO Feedback(thoughts, user_id, study_id, session_id) VALUES (?, ?, ?, ?)', (feedback, user_id, study_id, session_id))
        if cursor.rowcount == 1:
            conn.commit()
            return True
        else:
            conn.rollback()
            return False
    except Exception:
        return False