import sqlite3
from pathlib import Path
from tqdm import tqdm

def make_dicts(cursor, row): return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))

conn = sqlite3.connect('data.db')
conn.row_factory = make_dicts

actions = conn.execute('SELECT * From Actions').fetchall()
for action in tqdm(actions):
	action_id = action['id']
	new_urls = []
	must_update = False
	for key in [f'in_context{i}' for i in range(1, 4)]:
		if key not in action:
			print('missing required column: ', key)
			exit(1)
		old_url = action[key]
		if 'googleapis.com/action-atlas/' in old_url:
			must_update = True
			new_url = 'https://storage.googleapis.com/oe-training-yt-crawl/VideoNet/' + Path(old_url).name
		else:
			new_url = old_url
		new_urls.append(new_url)
	if must_update:
		conn.execute('UPDATE Actions SET in_context1 = ?, in_context2 = ?, in_context3 = ? WHERE id = ?', new_urls + [action_id])
		conn.commit()

questions = conn.execute('SELECT * FROM Questions').fetchall()
for question in tqdm(questions):
	q_id, q_url = question['id'], question['video_url']
	if 'googleapis.com/action-atlas/' in q_url:
		q_url = 'https://storage.googleapis.com/oe-training-yt-crawl/VideoNet/' + Path(q_url).name
		conn.execute('UPDATE Questions SET video_url = ? WHERE id = ?', (q_url, q_id))
		conn.commit()

conn.close()
