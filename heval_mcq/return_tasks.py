import sqlite3, os, time, random

if __name__ == '__main__':
    # set up db connection
    DATABASE = os.environ.get('DATABASE', '/persistent/data.db')
    conn = sqlite3.connect(DATABASE)
    def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))
    conn.row_factory = make_dicts
    
    # get all 'returned' / timed-out assignments
    i = 0
    while i < 10:
        conn.execute('BEGIN EXCLUSIVE TRANSACTION')
        try:
            cursor = conn.cursor()
            cursor.execute('''
                            SELECT id, question_id FROM Assignments
                            WHERE completed = 0 AND assigned_at < datetime('now', '-30 minutes')
                            ''')
            rows = cursor.fetchall()
            for r in rows:
                # decrement num of Prolific users assigned this action
                question = cursor.execute('SELECT assigned FROM Questions WHERE id = ?', (r['question_id'],)).fetchone()
                if not question: raise Exception
                cursor.execute('UPDATE Questions SET assigned = ? WHERE id = ?', (question['assigned'] - 1, r['question_id']))
                if cursor.rowcount != 1: raise Exception
                
                # delete assignment
                cursor.execute('DELETE FROM Assignments WHERE id = ?', (r['id'],))
                if cursor.rowcount != 1: raise Exception
            conn.commit()
            exit(0)
        except sqlite3.OperationalError as e:
            print("ERROR: unable to return tasks: ", e)
            conn.rollback()
            time.sleep(12 + random.uniform(1, 3) * i)
            i += 1
        except Exception:
            exit(1)