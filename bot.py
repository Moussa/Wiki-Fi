import pymongo
import wiki_api
from config import config

connection = pymongo.Connection('localhost', 27017)

wiki_dict = {}
for wiki in config:
	db = connection[config[wiki]['db_name']]
	api = wiki_api.API(config[wiki]['api_url'], config[wiki]['username'], config[wiki]['password'])
	print('Successfully loaded ' + wiki)
	wiki_dict[wiki] = {'db': db, 'api': api}

def get_user_id(db, username):
	user = db['users'].find_one({'username': username})
	if user is None:
		user_id = db['users'].insert({'username': username})
	else:
		user_id = user['_id']

	return user_id

def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0:
		return None
	return (db['edits'].find({}, sort=[('date', pymongo.DESCENDING )]).limit(1))[0]['timestamp']

def insert_recent_edits():
	for wiki in wiki_dict:
		db = wiki_dict[wiki]['db']
		api = wiki_dict[wiki]['api']

		last_edit = get_last_edit_datetime(db)
		recent_edits = api.get_recent_changes(last_edit)
		recent_edits = recent_edits[:-1]  # remove last duplicate edit

		for edit in recent_edits:
			user_id = get_user_id(db, edit['user'])
			d, date_index_string = api.get_date_from_string(edit['timestamp'])
			output = {'user_id': user_id,
					  'ns': edit['ns'],
					  'revid': edit['revid'],
					  'date': d,
					  'title': edit['title'],
					  'date_string': date_index_string,
					  'timestamp': edit['timestamp'],
					  'comment': edit['comment']
					  }
			db['edits'].insert(output, safe=True)


if __name__ == '__main__':
	insert_recent_edits()
