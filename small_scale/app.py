from flask import Flask, request, render_template, g
from sqlite3 import Connection
import utils

import sqlite3, os

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
PROLIFIC_COMPLETION_CODE = os.environ.get('PROLIFIC_COMPLETION_CODE')

# **** BEGIN DATABASE ****
def get_db() -> Connection:
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    
    def make_dicts(cursor, row):
        return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
    db.row_factory = make_dicts

    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
# **** ENDOF DATABASE ****

# **** BEGIN PAGE SERVING ****
ERROR_MSG = "<h1> This page is only accessible through Prolific. </h1> <p> If you reached this page through Prolific, please report our study as having an error in the setup. </p>"

@app.route('/')
def show_error():
    return ERROR_MSG

@app.route('/task')
def show_task():
    """
    Renders landing page for a Prolific user if given a URL with the required params (PROLIFIC_PID, STUDY_ID, SESSION_ID). 
    
    Otherwise renders an error message.

    Note that the "landing page" contains the entirety of the task; this is the only page the Prolific user will interact with.
    """
    # Ensure that we have tasks remaining
    work_available = utils.has_unassigned_tasks(get_db())
    if isinstance(work_available, str): return work_available   # check for SQL error
    if not work_available:
        return '<h1 style="text-align:center; margin-top:2rem;"> Apologies, we have no tasks remaining.</h1>'

    # Extract identifiers provided by Prolific; see https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    if not user_id or not study_id or not session_id:
        return ERROR_MSG
    
    # get action and token
    action_info: tuple[int, str, str, str | None, str] | str = utils.get_action_and_token(get_db(), user_id, study_id, session_id)
    if isinstance(action_info, str): return action_info
    action_id, action_name, domain_name, subdomain, token = action_info

    # render webpage
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'token': token, 'subdomain': subdomain,
              'action_id': action_id, 'action_name': action_name, 'domain_name': domain_name, 'domain_name_lowercase': domain_name.lower()}
    return render_template('start.html', **kwargs)

@app.route('/process', methods=['POST'])
def process_action():
    """
    Adds the specified 7 clips to Clips database.
    Assumes that `request.form` contains validated arguments ('url{i}', 'start{i}', and 'end{i}' times, where i=1..7).

    Upon success, returns 200 status with HTML for survey finish page. Upon failure, returns non-200 code with a helpful error message in string form.
    """
    args = request.form
    user_id, study_id, session_id = args.get('user_id'), args.get('study_id'), args.get('session_id')
    if not user_id or not study_id or not session_id:
        return 'An error occured while accessing the Prolific identifiers associated with you.', 400

    clips: list[tuple[str, float, float]] = []
    for i in range(1, 8):
        url, start, end = args.get(f'url{i}', type=str), args.get(f'start{i}'), args.get(f'end{i}')
        if url is None or start is None or end is None:
            return f'An error occured while processing the clips you found. We could not locate the url, start, or end time for video #{i}.', 400
        start, end = utils.convert_to_seconds(start), utils.convert_to_seconds(end)
        clips.append((url, start, end))
    
    action_id = args.get('action_id', type=int)
    if action_id is None:
        return 'An error occured while processing the clips you found. We could not locate the action these clips are about.', 400
    
    if utils.add_clips(get_db(), clips, action_id):
        return 'An error occured while updating our database to include the clips you found.', 500
    
    token = args.get('token')
    if token is None:
        return 'We were unable to verify that you were directed to this survey from Prolific.', 400

    if not isinstance(token, str) or not utils.verify_token(get_db(), token, user_id, study_id, session_id):
        return 'An error occured while verifying that you were directed to this survey from Prolific.', 400
    
    if not utils.use_token(get_db(), user_id, study_id, session_id):
        return 'An error occured while marking your survey as finished.', 400
    
    feedback = args.get('feedback')
    if feedback and feedback != '':
        utils.add_feedback(get_db(), feedback, user_id, study_id, session_id)
    
    return f'https://app.prolific.com/submissions/complete?cc={PROLIFIC_COMPLETION_CODE}', 200

# **** ENDOF PAGE SERVING ****