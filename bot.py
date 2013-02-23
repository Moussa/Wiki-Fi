# -*- coding: utf-8 -*-
import datetime, sys, re
import pymongo
import wiki_api
from config import config
from werkzeug.contrib.cache import MemcachedCache

cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.Connection(config['db']['host'], config['db']['port'], w=1)

dateRE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z')

def get_date_from_string(date_string):
	res = dateRE.search(date_string)
	if not res:
		return None
	year = int(res.group(1))
	month = int(res.group(2))
	day = int(res.group(3))
	hour = int(res.group(4))
	minute = int(res.group(5))
	second = int(res.group(6))
	d = datetime.datetime(year, month, day, hour, minute, second)

	return d

def load(wiki):
	db = connection[config['wikis'][wiki]['db_name']]
	w_api = wiki_api.Wiki_API(config['wikis'][wiki]['api_url'], config['wikis'][wiki]['username'], config['wikis'][wiki]['password'])
	print('Successfully loaded ' + wiki)
	return db, w_api

def get_user_id(db, username, wiki):
	user = db['users'].find_one({'username': username}, fields=[])
	if user is None:
		user_id = db['users'].insert({'username': username})
		cache.delete('wiki-data_userlist_{0}'.format(wiki))
		cache.delete('wiki-data_userwikislist_{0}'.format(username))
	else:
		user_id = user['_id']

	return user_id

def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0:
		return None
	return (db['edits'].find(fields=['timestamp'], sort=[('date', pymongo.DESCENDING)]).limit(1))[0]['timestamp']

def seed(wiki):
	db, w_api = load(wiki)

	users = w_api.get_users(edited_only=True)

	for user in users:
		username = user['name']
		if db['users'].find_one({'username': username}, fields=[]) is None:
			wiki_registration = user['registration']
			timestamp = get_date_from_string(wiki_registration)
			db['users'].insert({'username': username, 'registration': timestamp})

	# define cutoff date so that edits made during seeding are not missed
	cutoff_date = datetime.datetime.now()
	print('cutoff date for edits is: ' + str(cutoff_date))

	for user in db['users'].find():
		print('Inserting edits for ' + user['username'].encode('utf-8'))
		edits = w_api.get_user_edits(user['username'])
		for edit in edits:
			timestamp = get_date_from_string(edit['timestamp'])
			if timestamp < cutoff_date:
				output = {'user_id': user['_id'],
                          'ns': edit['ns'],
                          'revid': edit['revid'],
                          'title': edit['title'],
                          'timestamp': timestamp
                          }
				db['edits'].insert(output)

def update(wiki):
	db, w_api = load(wiki)

	last_edit = get_last_edit_datetime(db)
	recent_edits = w_api.get_recent_changes(last_edit)
	datenow = datetime.datetime.now()

	for edit in recent_edits:
		# check if edit has already been inserted into db
		if db['edits'].find_one({'revid': edit['revid']}, fields=[]):
			continue
		user_id = get_user_id(db, edit['user'], wiki)
		timestamp = get_date_from_string(edit['timestamp'])
		output = {'user_id': user_id,
                  'ns': edit['ns'],
                  'revid': edit['revid'],
                  'title': edit['title'],
                  'timestamp': timestamp
                  }
		print('Inserting revid ' + str(edit['revid']) + ': \'' + edit['title'].encode('utf-8') + '\' by ' + edit['user'].encode('utf-8'))
		db['edits'].insert(output)
		# delete cache key to load fresh data on next retrieval
		cache.delete('wiki-data_{0}_{1}'.format(edit['user'], wiki))
	# update last_updated time
	db['metadata'].update({'key': 'last_updated'}, {'$set': {'last_updated': datenow}}, upsert=True)
	cache.set('wiki-metadata_last_updated_' + wiki, datenow, timeout=0)


if __name__ == '__main__':
	if sys.argv[1] == 'seed':
		seed(sys.argv[2])
	elif sys.argv[1] == 'update':
		update(sys.argv[2])
