"""
Reassigns jobs that have been assigned for an hour but not finished back into the pool of available tasks.

We assume this subset of jobs were 'returned' by the Prolific user.
"""
import sqlite3, os

if __name__ == '__main__':
    # set up db connection
    DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
    conn = sqlite3.connect(DATABASE)
    def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
    conn.row_factory = make_dicts
    
    # get all 'returned' / timed-out assignments
    conn.execute('BEGIN EXCLUSIVE TRANSACTION')
    try:
        cursor = conn.cursor()
        cursor.execute('''
                        SELECT id, action_id, assigned_at FROM Assignments
                        WHERE completed = 0 AND assigned_at < datetime('now', '-1 hour')
                        ''')
        rows = cursor.fetchall()
        for r in rows:
            # decrement num of Prolific users assigned this action
            action = cursor.execute('SELECT assigned FROM Actions WHERE id = ?', (r['action_id'],)).fetchone()
            if not action: raise Exception
            cursor.execute('UPDATE Actions SET assigned = ? WHERE id = ?', (action['assigned'] - 1, r['action_id']))
            if cursor.rowcount != 1: raise Exception
            
            # delete assignment
            cursor.execute('DELETE FROM Assignments WHERE id = ?', (r['id'],))
            if cursor.rowcount != 1: raise Exception
        conn.commit()
    except:
        conn.rollback()
        exit(1)