from flask import Flask, request, render_template, g
import sqlite3, os, subprocess
import heval.hutils as hutils
# import hutils

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
PROLIFIC_COMPLETION_CODE = os.environ.get('PROLIFIC_COMPLETION_CODE')

# **** BEGIN DATABASE ****
def get_db() -> sqlite3.Connection:
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

@app.route('/return-tasks-ostrich')
def return_tasks():
    if request.args.get('animal') == 'beaver':
        subprocess.run(['python', '/opt/render/project/heval/small_scale/return_tasks.py'])
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
    work_available = hutils.has_unassigned_tasks(get_db())
    if isinstance(work_available, str): return work_available   # check for SQL error
    if not work_available:
        return '<h1 style="text-align:center; margin-top:2rem;"> Apologies, we have no tasks remaining.</h1>'

    # Extract identifiers provided by Prolific; see https://researcher-help.prolific.com/en/article/866615
    user_id: str | None = request.args.get('PROLIFIC_PID')
    study_id: str | None = request.args.get('STUDY_ID')
    session_id: str | None = request.args.get('SESSION_ID')
    tmp = request.args.get('DEFN', default='').upper()
    include_defn: int | None = 1 if tmp == 'YES' else (0 if tmp == 'NO' else None)
    num_ice: int | None = request.args.get('NUM', type=int)
    if not user_id or not study_id or not session_id or include_defn is None or num_ice not in {0, 1, 2, 3}:
        return ERROR_MSG
    
    # get assignment
    assignment_info: tuple[str, int] | str = hutils.get_assignment(get_db(), user_id, study_id, session_id)
    if isinstance(assignment_info, str):
        return assignment_info
    assignment_uuid, question_id = assignment_info
    
    # get question and action details for our assignment
    question_details: dict[str] | str = hutils.get_question_details(get_db(), question_id)
    if isinstance(question_details, str):
        return question_details
    if not include_defn: 
        question_details['definition'] = None

    # render webpage
    kwargs = {'user_id': user_id, 'study_id': study_id, 'session_id': session_id, 'num_ice': num_ice,
              'assignment_uuid': assignment_uuid, 'question_id': question_id, **question_details}
    return render_template('start.html', **kwargs)

@app.route('/submit', methods=['POST'])
def submit_annotations():
    """
    Updates database to include user's completed annotations. Returns HTML to render a final page that helps user get Prolific completion credit.
    """
    args = request.form
    print(args)
    user_id, study_id, session_id = args.get('user_id'), args.get('study_id'), args.get('session_id')
    if user_id is None or study_id is None or session_id is None:
        return "Your submission was corrupted. Please try submitting again. If the issue persists, message us no Prolific."
    
    question_id, assignment_uuid, guess = args.get('question_id', type=int), args.get('assignment_uuid'), args.get('guess')
    classification = 1 if guess == "yes" else (0 if guess == "no" else -1)
    if classification == -1: return "Your submission was corrupted -- we recieved your guess as a value other than 'yes' or 'no'. Please try submitting again. If the issue occurs again, message us on Prolific."
    if question_id is None or assignment_uuid is None or guess is None:
        return "Your submission was corrupted. Please try submitting again. If the issue persists, message us on Prolific."
    if err := hutils.log_classification(get_db(), question_id, assignment_uuid, classification):
        return err
    
    kwargs = {'completion_code': PROLIFIC_COMPLETION_CODE}
    return render_template('finish.html', **kwargs)
    
