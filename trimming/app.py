from flask import Flask, request, render_template, g
from sqlite3 import Connection
import sqlite3, os, subprocess
import tutils

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

ERROR_MSG = "<h1> This page is only accessible through Prolific. </h1> <p> If you reached this page through Prolific, please report our study as having an error in the setup. </p>"

@app.route('/')
def show_error():
    return ERROR_MSG

@app.route('/return-tasks-ostrich')
def return_tasks():
    if request.args.get('animal') == 'beaver':
        subprocess.run(['python', '/opt/render/project/src/trimming/return_tasks.py'])
        return 'Returned (if applicable)', 200
    else:
        return 'Wrong Password', 401

@app.route('/task')
def show_task():
    """
    Renders landing page for a Prolific user if given a URL with the required params (PROLIFIC_PID, STUDY_ID, SESSION_ID). 
    
    Otherwise renders an error message.
    
    Note that the "landing page" contains the entirety of the task; the only other page the user will interact with is the "finish page".
    """
    # Extract identifiers provided by Prolific; see https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    if not user_id or not study_id or not session_id:
        return ERROR_MSG
    
    # get action
    action_info: tuple[int, str, str, str | None, str] | str = tutils.get_action(get_db(), user_id, study_id, session_id)
    if isinstance(action_info, str): return action_info
    action_id, action_name, domain_name, subdomain = action_info
    if subdomain in set(['NULL', 'Null', 'null']): subdomain = None

    # get clips
    clips: tuple[list[dict], list[dict]] | str = tutils.get_clips(get_db(), action_id)
    if isinstance(clips, str): return clips
    good_clips, bad_clips = clips

    # render webpage
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'action_id': action_id,
              'action_name': action_name, 'domain_name': domain_name, 'subdomain': subdomain,
              'good_clips': good_clips, 'bad_clips': bad_clips, 'num_good': len(good_clips), 'num_bad': len(bad_clips)}
    return render_template('start.html', **kwargs)

@app.route('/submit', methods=['POST'])
def submit_trims():
    """
    Adds the user trimming for the clips to the Trimmings database.
    
    Upon success, redirects user to survey finish page. Upon failure, returns error message.
    """
    args = request.form
    user_id, study_id, session_id, action_id = args.get('user_id'), args.get('study_id'), args.get('session_id'), args.get('action_id', type=int)
    if not user_id or not study_id or not session_id or action_id is None:
        return 'An error occured while accessing the Prolific identifiers associated with you.', 400
    
    trims: list[tuple[str, float, float]] = []
    num_trims = args.get('num_trims', type=int)
    for i in range(1, num_trims + 1):
        unique = args.get(f'uuid{i}')
        cushion_start, start, end = args.get(f'cushion_start{i}', type=float), args.get(f'start{i}', type=float), args.get(f'end{i}', type=float)
        onscreen: str = args.get(f'checked{i}', type=str)
        if unique is None or cushion_start is None or start is None or end is None or onscreen is None:
            return 'An error occured while parsing your submission.', 400
        onscreen: int = int(onscreen.lower() == 'true')
        final_start, final_end = cushion_start + start, cushion_start + end
        trims.append((unique, final_start, final_end, onscreen))
    
    if tutils.add_trimmings(get_db(), trims):
        return 'An error occured while saving your annotations. Please try submitting again. If the issue persists, reach out to us on Prolific.', 500
    
    if tutils.mark_finished(get_db(), user_id, action_id):
        return 'An error occured while marking your task as finished. Please try submitting again. If the issue persists, reach out to us on Prolific.', 500
    
    feedback = args.get('feedback')
    if feedback and feedback != '':
        tutils.add_feedback(get_db(), feedback, user_id, study_id, session_id)

    return render_template('finish.html', completion_code=PROLIFIC_COMPLETION_CODE), 200