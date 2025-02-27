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
    Returns True if Actions table has at least one row with a value of 1 in the 'status' column. Otherwise returns False.

    If an issue occurs while executing the SQL query, a string error message is returned instead.
    """
    result: dict[str, int] | None = query_db(c, 'SELECT COUNT(*) as cnt FROM Actions WHERE status = 1', one=True)
    if not result:
        return 'An error occured while trying to check if we have any tasks left for you to do.'
    return result['cnt'] > 0

def assign_token(conn: Connection, user_id: str, study_id: str, session_id: str) -> str | bool:
    """
    Generates a random verification token for this Prolific session. 
    
    Returns it as a string upon success; returns the boolean False if a failure occured.
    """
    alphabet = string.ascii_letters + string.digits
    token: str = "".join(secrets.choice(alphabet) for _ in range(16))
    try:
        cursor = conn.execute('INSERT INTO Sessions(token, user_id, study_id, session_id) VALUES (?, ?, ?, ?);', 
                          (token, user_id, study_id, session_id))
        r = cursor.rowcount
        conn.commit()
        return token if r == 1 else False
    except Exception as e:
        return False
    
def assign_action(conn: Connection, user_id: str, study_id: str, session_id: str) -> tuple[int, str] | str:
    """
    Assigns an action to the Prolific user with PID `user_id`.

    Upon success, returns 2-tuple containing [0] primary key of that action (as an integer) in the Actions table and [1] action name.
    
    Upon a SQL failure, returns a string error message.
    """
    conn.execute('BEGIN TRANSACTION;')
    available_actions: list[dict[str, int]] | None = query_db(conn, 'SELECT id, name FROM Actions WHERE status = 1 ORDER BY RANDOM() LIMIT 30;')
    if not available_actions:
        conn.execute('ROLLBACK;')
        return 'An error occured while assigning you a task. Please reload this page and try again. If the issue persists, please exit the survey. Our apologies.'
    for action in available_actions:
        action_id, action_name = action['id'], action['name']
        cursor = conn.execute('UPDATE Actions SET status = 2, user_id = ?, study_id = ?, session_id = ? WHERE id = ? AND status = 1;', (user_id, study_id, session_id, action_id))
        if cursor.rowcount == 1:
            conn.execute('COMMIT;')
            return action_id, action_name
    
    conn.execute('ROLLBACK;')
    return 'We were unable to assign you a task. Please reload this page and try again. If the issue persists, please exit the survey. Our apologies.'

def add_clips(conn: Connection, clips: list[tuple[str, float, float]], action_id: int) -> int:
    """
    Adds specified `clips` to Clips database for the action whose primary key value in Actions is `action_id`. 
    
    Returns 0 on success and 1 on failure.
    """
    conn.execute('BEGIN TRANSACTION;')
    for i in range(len(clips)):
        url, start, end = clips[i]
        cursor = conn.execute('INSERT INTO Clips(action_id, url, start, end) VALUES (?, ?, ?, ?);', (action_id, url, start, end))
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
    res: dict | None = query_db(c, 'SELECT token FROM Sessions WHERE user_id = ? AND study_id = ? AND session_id = ? AND finished = 0;', (user_id, study_id, session_id), one=True)
    return True if res and res['token'] == token else False

def use_token(conn: Connection, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Marks token as used so the user can't garner multiple Prolific confirmation codes from completing a single Prolific survey.

    Returns boolean indicating if this operation was successful.
    """
    try:
        cursor = conn.execute('UPDATE Sessions SET finished = 1 WHERE user_id = ? AND study_id = ? AND session_id = ? AND finished = 0;', (user_id, study_id, session_id))
        r = cursor.rowcount
    except Exception as e:
        return False

    if r == 1:
        conn.commit()
        return True
    else:
        conn.rollback()
        return False