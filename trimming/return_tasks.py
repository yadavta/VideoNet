"""
Reassigns jobs that have been assigned for an hour but not finished back into the pool of available tasks.

We assume this subset of jobs were 'returned' by the Prolific user.
"""
import sqlite3, os, datetime

if __name__ == '__main__':
    # set up db connection
    DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
    conn = sqlite3.connect(DATABASE)
    cursor = conn.execute('''
                          UPDATE Actions 
                          SET assigned=0, finished=0, user_id=NULL, study_id=NULL, session_id=NULL, assigned_at=NULL
                          WHERE assigned = 1 AND finished = 0 AND assigned_at < datetime('now', '-1 hour')
                          ''')
    print(datetime.datetime.now().replace(microsecond=0), '\t', cursor.rowcount)
    conn.commit()
    conn.close()