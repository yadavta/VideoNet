"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
from sqlite3 import Connection
import secrets, string

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    """
    DOES NOT CLOSE `conn`. THAT IS RESPONSIBILITY OF THE CALLER.
    """
    cursor = conn.execute(query, args)
    rows = cursor.fetchall()
    return rows if not one else (rows[0] if rows else None)

def has_unassigned_tasks(c: Connection) -> bool | str:
    """
    Returns True if Actions table has at least one row with a value of 1 in the 'assigned' column. Otherwise returns False.

    If an issue occurs while executing the SQL query, a string error message is returned instead.
    """
    result: dict[str, int] | None = query_db(c, 'SELECT COUNT(*) as cnt FROM Actions WHERE assigned = 0', one=True)
    if not result:
        return 'An error occured while trying to check if we have any tasks left for you to do.'
    return result['cnt'] > 0

def get_action_and_token(conn: Connection, user_id: str, study_id: str, session_id: str) -> tuple[int, str, str, str] | str:
    """
    1. If no existing token, assign action & token and return them to user
    2. If token exists but has not been used, return existing action & token to user
    3. If token exists and has already been used, return an error

    Upon case 1 or 2, returns 5-tuple of action id, action name, domain name, subdomain and token.
    Upon case 3, returns string.
    """
    conn.execute('BEGIN TRANSACTION;')
    res = conn.execute('SELECT * FROM Actions WHERE user_id = ? AND study_id = ? AND session_id = ?', (user_id, study_id, session_id)).fetchall()

    if not res:
        # CASE 1
        error = 'An error occured while trying to assign you a task. Please reload this page and try again. If the issue persists, something is wrong on our end.'

        # attempt to find an available task
        actions = conn.execute('SELECT id, name, domain_name, subdomain FROM Actions WHERE assigned = 0 ORDER BY RANDOM() LIMIT 1').fetchall()
        if not actions: return error
        action_id, action_name, domain_name, subdomain = actions[0]['id'], actions[0]['name'], actions[0]['domain_name'], actions[0]['subdomain']

        # found an available task; attempt to assign it
        token = generate_token()
        cursor = conn.execute("UPDATE Actions SET assigned = 1, assigned_at = datetime('now'), token = ?, user_id = ?, study_id = ?, session_id = ? WHERE id = ? AND assigned = 0", (token, user_id, study_id, session_id, action_id))
        if cursor.rowcount == 1:
            conn.execute('COMMIT;')
            return action_id, action_name, domain_name, subdomain, token
        
        # unable to assign the task; rollback changes and return error
        conn.execute('ROLLBACK;')
        return error
    elif int(res[0]['finished']) == 0:
        # CASE 2
        return int(res[0]['id']), res[0]['name'], res[0]['domain_name'], res[0]['subdomain'], res[0]['token']
    else:
        # CASE 3
        return 'You have already completed this Prolific task.'

def generate_token() -> str:
    """
    Returns a randomized 16 character token.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))

def add_clips(conn: Connection, clips: list[tuple[str, float, float]], action_id: int) -> int:
    """
    Adds specified `clips` to Clips database for the action whose primary key value in Actions is `action_id`. 
    
    Returns 0 on success and 1 on failure.
    """
    conn.execute('BEGIN TRANSACTION;')
    for i in range(len(clips)):
        url, start, end = clips[i]
        cursor = conn.execute('INSERT INTO Clips(action_id, url, start, end) VALUES (?, ?, ?, ?)', (action_id, url, start, end))
        if cursor.rowcount != 1: 
            conn.execute('ROLLBACK;')
            return 1
    conn.execute('COMMIT;')
    return 0

def verify_token(c: Connection, token: str, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Verifies if provided `token` is the confirmation token stored in database for this Prolific session.

    Returns boolean indicating if this operation was successful.
    """
    res: dict | None = query_db(c, 'SELECT token FROM Actions WHERE user_id = ? AND study_id = ? AND session_id = ? AND finished = 0', (user_id, study_id, session_id), one=True)
    return True if res and res['token'] == token else False

def use_token(conn: Connection, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Marks token as used so the user can't garner multiple Prolific confirmation codes from completing a single Prolific survey.

    Returns boolean indicating if this operation was successful.
    """
    try:
        cursor = conn.execute('UPDATE Actions SET finished = 1 WHERE user_id = ? AND study_id = ? AND session_id = ? AND finished = 0', (user_id, study_id, session_id))
        r = cursor.rowcount
    except Exception:
        return False

    if r == 1:
        conn.commit()
        return True
    else:
        conn.rollback()
        return False
    
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

def convert_to_seconds(time: str) -> float:
    """
    Given a timestamp in MM:SS or seconds format, converts it to seconds format and returns as a float.
    """
    time = time.strip()
    if ':' not in time:
        return float(time)
    
    min, sec = time.split(':')
    return 60 * float(min) + float(sec)