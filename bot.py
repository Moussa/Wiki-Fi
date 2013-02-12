# -*- coding: utf-8 -*-
import datetime, sys
import pymongo
import wiki_api
from config import config
from werkzeug.contrib.cache import MemcachedCache

cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.Connection(config['db']['host'], config['db']['port'])

def load(wiki):
	db = connection[config['wikis'][wiki]['db_name']]
	api = wiki_api.API(config['wikis'][wiki]['api_url'], config['wikis'][wiki]['username'], config['wikis'][wiki]['password'])
	print('Successfully loaded ' + wiki)
	return db, api

def get_user_id(db, username):
	user = db['users'].find_one({'username': username})
	if user is None:
		user_id = db['users'].insert({'username': username})
		cache.delete('wiki-data_allusers')
	else:
		user_id = user['_id']

	return user_id

def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0:
		return None
	return (db['edits'].find({}, sort=[('date', pymongo.DESCENDING)]).limit(1))[0]['timestamp']

def seed(wiki):
	db, api = load(wiki)

	users = api.get_users(edited_only=True)

	for user in users:
		username = user['name']
		tfwiki_registration = user['registration']
		d, date_index_string = api.get_date_from_string(tfwiki_registration)
		if db['users'].find_one({'username': username}) is None:
			db['users'].insert({'username': username, 'registration': d}, safe=True)
		elif 'registration' not in db['users'].find_one({'username': username}):
			db['users'].update({'username': username}, {'registration': d})

	# define cutoff date so that edits made during seeding are not missed
	cutoff_date = datetime.datetime.now()
	print('cutoff date for edits is: ' + str(cutoff_date))

	for user in db['users'].find():
		print('Inserting edits for ' + user['username'].encode('utf-8'))
		edits = api.get_user_edits(user['username'])
		for edit in edits:
			d, date_index_string = api.get_date_from_string(edit['timestamp'])
			if d < cutoff_date:
				output = {'user_id': user['_id'],
						  'ns': edit['ns'],
						  'revid': edit['revid'],
						  'date': d,
						  'title': edit['title'],
						  'date_string': date_index_string,
						  'timestamp': edit['timestamp']
						  }
				db['edits'].insert(output, safe=True)

def update(wiki):
	db, api = load(wiki)

	last_edit = get_last_edit_datetime(db)
	recent_edits = api.get_recent_changes(last_edit)
	datenow = datetime.datetime.now()

	check_dupe = True
	for edit in recent_edits:
		if check_dupe:  # don't insert already existing edits on start date
			if edit['timestamp'] == last_edit:
				if db['edits'].find_one({'revid': edit['revid']}):
					continue
			else:
				check_dupe = False  # no more duplicate edits
		user_id = get_user_id(db, edit['user'])
		d, date_index_string = api.get_date_from_string(edit['timestamp'])
		output = {'user_id': user_id,
				  'ns': edit['ns'],
				  'revid': edit['revid'],
				  'date': d,
				  'title': edit['title'],
				  'date_string': date_index_string,
				  'timestamp': edit['timestamp']
				  }
		db['edits'].insert(output, safe=True)
		# delete cache key to load fresh data on next retrieval
		cache.delete('wiki-data_{0}_{1}'.format(edit['user'], wiki))
	# update last_updated time
	db['metadata'].update({'key': 'last_updated'}, {'$set': {'last_updated': datenow}}, upsert=True, safe=True)
	cache.set('wiki-metadata_last_updated_' + wiki, datenow, timeout=0)


if __name__ == '__main__':
	if sys.argv[1] == 'seed':
		seed(sys.argv[2])
	elif sys.argv[1] == 'update':
		update(sys.argv[2])
