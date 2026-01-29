"""
Utilities used by our web app.

These are (mostly) for specific purposes but are located here to limit the length of `app.py`.
"""
import uuid, time, json
from pathlib import Path
from sqlite3 import Connection

NUM_ANNOTATORS_PER_QUESTION = 1     # how many workers should answer each question
NEGATIVES_FILE = 'hard.txt'
DEFINITIONS_FILE = 'definitions.json'

def read_negatives():
    try:
        with open(NEGATIVES_FILE, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"ERROR: unable to open file holding negatives for VideoNet. we expected it to be at {NEGATIVES_FILE} \
            ... exiting early!")
        raise e
    
    try:
        # each line of this file should look like this: actionName, negative1, negative2, negative3
        # lines that begin with '#' are ignored when parsing
        negatives: dict[str, list[str]] = {}    # maps an action name to a list of negative action names
        for line in lines:
            if not line or line[0] == "#":
                continue
            actions = line.split(',')
            actions = [a.lower() for a in actions]
            action, negs = actions[0], actions[1:]
            negatives[action] = negs
    except Exception as e:
        print(f"ERROR: unable to parse negatives from {NEGATIVES_FILE} ... exiting early!")
        raise e
    
    negatives = {k: [li.strip() for li in v] for k, v in negatives.items()}     # remove trailing '\n' from last entry in each negatives list
    return negatives

def read_definitions():
    try:
        with open(DEFINITIONS_FILE, 'r') as f:
            definitions = json.load(f)
    except Exception as e:
        print(f"ERROR: unable to open file holding definitions of actions for VideoNet. We expected it to be at {DEFINITIONS_FILE} \
            ... exiting early!")
        raise e
    
    return definitions

def query_db(conn: Connection, query, args=(), one=False) -> list[dict] | dict | None:
    i = 0
    while i < 5:
        try:
            cursor = conn.execute(query, args)
            rows = cursor.fetchall()
            return rows if not one else (rows[0] if rows else None)
        except Exception:
            time.sleep(0.1)
            i += 1
    return None

def has_unassigned_tasks(c: Connection) -> bool | str:
    """
    Returns True if Questions table has at least one row with a value of < NUM_ANNOTATORS_PER_QUESTION in the 'assigned' column. Otherwise returns False.

    If an issue occurs while executing the SQL query, a string error message is returned instead.
    """
    result: dict[str, int] | None = query_db(c, f'SELECT COUNT(*) as cnt FROM Questions WHERE assigned < {NUM_ANNOTATORS_PER_QUESTION}', one=True)
    if not result:
        return 'An error occured while trying to check if we have any tasks left for you to do.'
    return result['cnt'] > 0

def get_assignment(conn: Connection, user_id: str, study_id: str, session_id: str) ->  tuple[str, int] | str:
    """
    1. If no existing assignment, assign question and return it to user
    2. If assigment exists but has not been completed, return existing question to user
    3. If assignment exists and has already been completed, return an error

    Upon case 1 or 2, returns assignment 2-tuple of assignment UUID and question ID.
    Upon case 3, returns error message.
    """
    res = conn.execute('SELECT * FROM Assignments WHERE user_id = ? AND study_id = ? AND session_id = ?', (user_id, study_id, session_id)).fetchall()

    if not res:
        # CASE 1
        error = 'NOTICE: An error occured while trying to assign you a task. Please reload this page and try again. If the issue persists, something is wrong on our end.'
        try:
            # find 10 available tasks from DB
            matched = False
            conn.execute('BEGIN EXCLUSIVE TRANSACTION;')
            questions = conn.execute('SELECT id, action_id, assigned FROM Questions WHERE assigned < ? ORDER BY RANDOM() LIMIT 10;', (NUM_ANNOTATORS_PER_QUESTION,)).fetchall()
            if not questions: 
                conn.rollback()
                return error
            
            # see if any of these 10 tasks work with our user (i.e., check for overlap)
            for q in questions:
                overlap = conn.execute('SELECT * FROM Assignments WHERE action_id = ? AND user_id = ?', (q['action_id'], user_id)).fetchall()
                if not overlap:
                    question_id, action_id = q['id'], q['action_id']
                    curr_assigned = q['assigned']
                    matched = True
                    break
            
            # could not find an available task
            if not matched:
                return 'NOTICE: We have run out of tasks for you. Apologies.'

            # found an available task; attempt to assign it
            unique = str(uuid.uuid4())
            cursor1 = conn.execute('UPDATE Questions SET assigned = ? WHERE id = ?', (int(curr_assigned) + 1, question_id))
            cursor2 = conn.execute("INSERT INTO Assignments(question_id, action_id, user_id, study_id, session_id, uuid, assigned_at, completed) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 0)", 
                                   (question_id, action_id, user_id, study_id, session_id, unique))
            if cursor1.rowcount == 1 and cursor2.rowcount == 1:
                conn.commit()
                return unique, question_id
                
            # unable to assign the task; rollback changes and return error
            conn.rollback()
            return error
        except Exception as e:
            conn.rollback()
            print(f'ERROR: unable to get assignment for user {user_id} due to exception: ', e)
            return error
    elif int(res[0]['completed']) == 0:
        return res[0]['uuid'], res[0]['question_id']
    else:
        # CASE 3
        return 'NOTICE: You have already completed this Prolific task.'
    
def get_question_details(conn: Connection, question_id: int, negs: dict[str, list[str]], defs: dict[str, str]) -> dict[str] | str:
    """
    Returns dictionary with information on question and action on success.
    Returns error message on failure.
    """
    q: dict | None = query_db(conn, 'SELECT * FROM Questions WHERE id = ?', (question_id, ), one=True)
    if not q:
        print(q)
        return "Unable to retrieve survey details. Please reload the page to try again."
    action_id = q['action_id']
    
    a: dict | None = query_db(conn, 'SELECT * FROM Actions where id = ?', (action_id, ), one=True)
    if not a:
        return "Unable to retrieve survey details. Please reload the page to try again."
    
    gt_action_id, gt_action_name = a['id'], a['name']
    test_video_uuid = Path(q['video_url']).stem
    
    mcq_options: list[str] = negs[gt_action_name.lower()].copy()                       # init to length 3
    positive_idx = uuid.UUID(test_video_uuid).int % len(mcq_options)
    mcq_options.insert(positive_idx, gt_action_name.lower())                    # now length 4
    mcq_definitions: list[str] = [defs[action.lower()] for action in mcq_options]
    mcq_answer: str = chr(ord('A') + positive_idx)
    
    assert len(mcq_options) == len(mcq_definitions)
    
    return {
        'action_id': gt_action_id, 'name': gt_action_name, 'domain': a['domain'], 'question_id': q['id'], 'question_video': q['video_url'],
        'mcq_options': mcq_options, 'mcq_definitions': mcq_definitions, 'mcq_answer': mcq_answer, 'num_options': len(mcq_options)
    }
    
def log_classification(conn: Connection, question_id: str, assignment_uuid: str, guess_action: str, guess_letter: str, ground_truth: str) -> int | str:
    """
    Updates this Assignment to be finished and denote the user's guess. Increments the `finished` field for this Question.
    
    Returns 0 on success. Returns an error message on failure.
    """
    i = 0
    while i < 5:
        try:
            conn.execute('BEGIN EXCLUSIVE TRANSACTION')
            res = conn.execute('SELECT completed FROM Assignments where uuid = ?', (assignment_uuid,)).fetchone()
            if res is None:
                return "We were unable to locate the task assigned to you. Please message us on Prolific."
            if int(res['completed']) == 1:
                return "You have already submitted this task. Please NOCODE the submission on Prolific and message us. \
                    We will ensure that you get paid for your work."
            
            res = conn.execute('SELECT finished, ground_truth FROM Questions WHERE id = ?', (question_id,)).fetchall()
            if len(res) != 1:
                return "We were unable to locate the question you answered. Please message us on Prolific."
            curr_finished = int(res[0]['finished'])
            
            cursor = conn.execute('UPDATE Questions SET finished = ? WHERE id = ?', (curr_finished + 1, question_id))
            if cursor.rowcount != 1:
                conn.rollback()
                return "We were unable to update our database to reflect that you finished the study. Please message us on Prolific."
            
            accurate = int(guess_letter == ground_truth)
            cursor = conn.execute('UPDATE Assignments SET completed = 1, guess_action = ?, guess_letter = ?, accurate = ? WHERE uuid = ?', 
                                  (guess_action, guess_letter, accurate, assignment_uuid))
            if cursor.rowcount != 1:
                conn.rollback()
                return "We were unable to record your answer in our database. Please message us on Prolific."
            
            conn.commit()
            return 0
        except Exception as e:
            conn.rollback()
            print(f'EXCEPTION: unable to log classification for UUID {assignment_uuid}:', e)
            time.sleep(0.1 + 0.03 * i)
            i += 1
    
    return "We were unable to connect to our database. Please wait a few seconds then try submitting again. Apologies."
            
def add_feedback(conn: Connection, feedback: str, user_id: str, study_id: str, session_id: str) -> bool:
    """
    Logs user feedback.

    Returns boolean indicating if operation was successful.
    """
    i = 0
    while i < 3:
        try:
            cursor.execute('BEGIN IMMEDIATE')
            cursor = conn.execute('INSERT INTO Feedback(thoughts, user_id, study_id, session_id) VALUES (?, ?, ?, ?)', (feedback, user_id, study_id, session_id))
            if cursor.rowcount == 1:
                conn.commit()
                return True
            else:
                raise Exception
        except Exception:
            conn.rollback()
            time.sleep(0.1 + 0.03 * i)
            i += 1
    return False