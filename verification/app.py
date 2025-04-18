from flask import Flask, request, render_template, g
from sqlite3 import Connection
import sqlite3, os, subprocess
import vutils

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
PROLIFIC_COMPLETION_CODE = os.environ.get('PROLIFIC_COMPLETION_CODE', 'CTDHGYQX')

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

ERROR_MSG = "<h1> This page is only accessible through Prolific. </h1> <p> If you reached this page through Prolific, please report our study as having an error in the setup. </p>"

@app.route('/')
def show_error():
    return ERROR_MSG

@app.route('/return-tasks-ostrich')
def return_tasks():
    if request.args.get('animal') == 'beaver':
        subprocess.run(['python', '/opt/render/project/src/verification/return_tasks.py'])
        return 'Returned (if applicable)', 200
    else:
        return 'Wrong Password', 401

@app.route('/task')
def show_task():
    """
    Renders landing page for a Prolific user if given a URL with the required params (PROLIFIC_PID, STUDY_ID, SESSION_ID). 
    
    Otherwise renders an error message.

    Note that the "landing page" contains the entirety of the task; this is the only page the Prolific user will interact with.
    """
    # Ensure that we have tasks remaining
    work_available = vutils.has_unassigned_tasks(get_db())
    if isinstance(work_available, str): return work_available   # check for SQL error
    if not work_available:
        return '<h1 style="text-align:center; margin-top:2rem;"> Apologies, we have no tasks remaining.</h1>'

    # Extract identifiers provided by Prolific; see https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    if not user_id or not study_id or not session_id:
        return ERROR_MSG
    
    # get action
    action_info = vutils.get_action(get_db(), user_id, study_id, session_id)
    if isinstance(action_info, str): return action_info
    action_id, action_name, domain_name, subdomain, defn = action_info

    # get clips
    clips: list[tuple[int, str]] | str = vutils.get_clips(get_db(), action_id)
    if isinstance(clips, str): return clips

    # render webpage
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'action_id': action_id, 'definition': defn,
              'action_name': action_name, 'domain_name': domain_name, 'subdomain': subdomain, 'clips': clips}
    return render_template('start.html', **kwargs)

@app.route('/submit', methods=['POST'])
def submit_annotations():
    """
    Adds the user annotations for the clips to the Clips database.

    Upon success, returns 200 status with HTML for survey finish page. Upon failure, returns non-200 code with a helpful error message in string form.
    """
    args = request.form
    user_id, study_id, session_id = args.get('user_id'), args.get('study_id'), args.get('session_id')
    if not user_id or not study_id or not session_id:
        return 'An error occured while accessing the Prolific identifiers associated with you.', 400
    
    clips: list[tuple[int, int]] = []
    num_clips = args.get('clip_count', type=int)
    for i in range(1, num_clips + 1):
        clip_id = args.get(f'c{i}-id', type=int)
        clip_annotation = args.get(f'c{i}', type=int)
        if not clip_id or not clip_annotation:
            return 'An error occured while parsing your form data.', 400
        clips.append((clip_id, clip_annotation))
    
    action_id = args.get('action_id', type=int)
    tmp = vutils.add_annotations(get_db(), clips, action_id, user_id, study_id, session_id)
    if tmp == 1:
        return 'An error occured while saving your annotations. Please try submitting again.', 400
    elif tmp == -1:
        return 'You have already submitted annotations for this clip. Please reach out to us on Prolific.', 400
    
    if vutils.mark_finished(get_db(), user_id, action_id):
        return 'An error occured while marking your task as finished. Please try submitting again.', 400
    
    feedback = args.get('feedback')
    if feedback and feedback != '':
        vutils.add_feedback(get_db(), feedback, user_id, study_id, session_id)

    kwargs = {'completion_code': PROLIFIC_COMPLETION_CODE}
    return render_template('finish.html', **kwargs)