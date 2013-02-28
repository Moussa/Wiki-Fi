# -*- coding: utf-8 -*-
import datetime, sys, re
import pymongo
import wiki_api
from config import config
from werkzeug.contrib.cache import MemcachedCache

cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.Connection(config['db']['host'], config['db']['port'], w=1)

dateRE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z')
linkRE = re.compile(r'\[\[(.+)\]\]')

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

def get_user_id(db, wiki, w_api, username, registration=None):
	user = db['users'].find_one({'username': username}, fields=[])
	if user is None:
		if registration is None:
			print username
			user = w_api.get_user(username)
			if 'registration' in user:
				registration = get_date_from_string(user['registration'])
			else:
				registration = None
		else:
			registration = get_date_from_string(registration)
		user_id = db['users'].insert({'username': username, 'registration': registration})
		cache.delete('wiki-fi_userlist_{0}'.format(wiki))
		cache.delete('wiki-fi_userwikislist_{0}'.format(username))
		cache.delete('wiki-fi_allusers')
	else:
		user_id = user['_id']

	return user_id

def get_page_id(db, wiki, title, ns):
	page = db['pages'].find_one({'title': title}, fields=[])
	if page is None:
		page_id = db['pages'].insert({'title': title, 'ns': ns})
	else:
		page_id = page['_id']

	return page_id

def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0:
		return None
	return (db['edits'].find(fields=['timestamp'], sort=[('timestamp', pymongo.DESCENDING)]).limit(1))[0]['timestamp']

def seed(wiki):
	db, w_api = load(wiki)

	users = w_api.get_users(edited_only=True)

	for user in users:
		username = user['name'].encode('utf-8')
		registration = user['registration']
		user_id = get_user_id(db, wiki, w_api, username, registration)

	# define cutoff date so that edits made during seeding are not missed
	cutoff_date = datetime.datetime.now()
	print('cutoff date for edits is: ' + str(cutoff_date))

	for user in users:
		print('Inserting edits for ' + user['name'].encode('utf-8'))
		user_id = get_user_id(db, wiki, w_api, user['name'].encode('utf-8'))
		edits = w_api.get_user_edits(user['name'])
		if edits is None:
			print('Invalid username. Skipping.')
			continue
		for edit in edits:
			if db['edits'].find_one({'revid': edit['revid']}, fields=[]):
				continue
			timestamp = get_date_from_string(edit['timestamp'])
			if timestamp < cutoff_date:
				page_id = get_page_id(db, wiki, edit['title'], edit['ns'])
				if edit['ns'] == 6 and ('new' in edit or edit['comment'].encode('utf-8').startswith("uploaded a new version of")):
					upload = True
				else:
					upload = False

				output = {'user_id': user_id,
                          'ns': edit['ns'],
                          'revid': edit['revid'],
                          'page_id': page_id,
                          'timestamp': timestamp,
                          'new_page': 'new' in edit,
                          'upload': upload
                          }
				db['edits'].insert(output)
	# update last_updated time
	datenow = datetime.datetime.now()
	db['metadata'].update({'key': 'last_updated'}, {'$set': {'last_updated': datenow}}, upsert=True)
	cache.set('wiki-fi_wiki_last_updated_' + wiki, datenow, timeout=0)

def update(wiki):
	db, w_api = load(wiki)

	last_edit = get_last_edit_datetime(db)
	print('Last edit time was: ' + str(last_edit))

	print('Fetching edits from wiki...')
	recent_edits = w_api.get_recent_changes(last_edit)
	print('Successfully fetched edits from wiki')

	datenow = datetime.datetime.now()
	last_seen_rcid_store = db['metadata'].find_one({'key': 'last_seen_rcid'}, fields=['value'])
	if last_seen_rcid_store is None:
		last_seen_rcid = 0
	else:
		last_seen_rcid = last_seen_rcid_store['value']

	for edit in recent_edits:
		# check if edit has already been inserted into db
		if edit['rcid'] <= last_seen_rcid:
			continue

		timestamp = get_date_from_string(edit['timestamp'])
		if edit['type'] == 'new':
			print('RCID: {0} - NEWPAGE: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))
			user_id = get_user_id(db, wiki, w_api, edit['user'].encode('utf-8'))
			page_id = get_page_id(db, wiki, edit['title'].encode('utf-8'), edit['ns'])
			output = {'user_id': user_id,
                      'ns': edit['ns'],
                      'revid': edit['revid'],
                      'page_id': page_id,
                      'timestamp': timestamp,
                      'new_page': True,
                      'upload': False
                      }
			db['edits'].insert(output)
			cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

		elif edit['type'] == 'edit':
			print('RCID: {0} - EDIT: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))
			user_id = get_user_id(db, wiki, w_api, edit['user'].encode('utf-8'))
			page_id = get_page_id(db, wiki, edit['title'].encode('utf-8'), edit['ns'])
			output = {'user_id': user_id,
                      'ns': edit['ns'],
                      'revid': edit['revid'],
                      'page_id': page_id,
                      'timestamp': timestamp,
                      'new_page': False,
                      'upload': False
                      }
			db['edits'].insert(output)
			cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

		elif edit['type'] == 'log':
			if edit['logtype'] == 'move':
				print('RCID: {0} - PAGEMOVE: {1} -> {2}'.format(edit['rcid'], edit['title'].encode('utf-8'), edit['move']['new_title'].encode('utf-8')))
				page_id = get_page_id(db, wiki, edit['title'].encode('utf-8'), edit['ns'])
				old_page_title = edit['title']
				new_page_title = edit['move']['new_title']
				new_page_ns = edit['move']['new_ns']

				# delete existing target page and any edits that referenced it
				target_page = db['pages'].find_one({'title': new_page_title})
				if target_page:
					db['pages'].remove({'_id': target_page['_id']})
					db['edits'].remove({'page_id': target_page['_id']})
				# rename oldpage to newpage
				db['pages'].update({'_id': page_id}, {'title': new_page_title, 'ns': new_page_ns})
				cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

				if 'suppressedredirect' not in edit['move']:
					# left behind a redirect
					print('RCID: {0} - REDIRECTCREATION: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))
					page_id = get_page_id(db, wiki, edit['title'].encode('utf-8'), edit['ns'])
					user_id = get_user_id(db, wiki, w_api, edit['user'].encode('utf-8'))
					output = {'user_id': user_id,
                              'ns': edit['ns'],
                              'revid': edit['revid'],
                              'page_id': page_id,
                              'timestamp': timestamp,
                              'new_page': True,
                              'upload': False
                              }
					db['edits'].insert(output)
					cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

			elif edit['logtype'] == 'upload':
				print('RCID: {0} - FILEUPLOAD: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))
				user_id = get_user_id(db, wiki, w_api, edit['user'].encode('utf-8'))
				page_id = get_page_id(db, wiki, edit['title'].encode('utf-8'), edit['ns'])
				output = {'user_id': user_id,
                          'ns': edit['ns'],
                          'revid': edit['revid'],
                          'page_id': page_id,
                          'timestamp': timestamp,
                          'new_page': edit['logaction'] == 'upload',
                          'upload': True
                         }
				db['edits'].insert(output)
				cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

			elif edit['logtype'] == 'delete':
				print('RCID: {0} - DELETION: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))
				page_id = get_page_id(db, wiki, edit['title'], edit['ns'])
				db['edits'].remove({'page_id': page_id})
				db['pages'].remove({'_id': page_id})
				cache.delete('wiki-fi_pagedata_{0}_{1}'.format(edit['title'].replace(' ', '_').encode('utf-8'), wiki))

			elif edit['logtype'] == 'newusers':
				print('RCID: {0} - NEWUSER: {1}'.format(edit['rcid'], edit['user'].encode('utf-8')))

			elif edit['logtype'] == 'block':
				print('RCID: {0} - BLOCK: {1}'.format(edit['rcid'], edit['title'].encode('utf-8')))

			else:
				print('MISSED')
				print edit
		else:
			print('MISSED')
			print edit

		last_seen_rcid = edit['rcid']

		cache.delete('wiki-fi_userdata_{0}_{1}'.format(edit['user'].replace(' ', '_').encode('utf-8'), wiki))
	# update last_updated time
	db['metadata'].update({'key': 'last_seen_rcid'}, {'$set': {'value': last_seen_rcid}}, upsert=True)
	db['metadata'].update({'key': 'last_updated'}, {'$set': {'last_updated': datenow}}, upsert=True)
	cache.set('wiki-fi_wiki_last_updated_' + wiki, datenow, timeout=0)


if __name__ == '__main__':
	if sys.argv[1] == 'seed':
		seed(sys.argv[2])
	elif sys.argv[1] == 'update':
		update(sys.argv[2])
