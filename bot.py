# -*- coding: utf-8 -*-
import datetime, sys, re, threading
import pymongo
import analyze
import wiki_api
import threadpool
from config import config
from werkzeug.contrib.cache import MemcachedCache

cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.MongoClient(config['db']['host'], config['db']['port'], w=1)

dateRE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z')
langArray = ['ar', 'cs', 'da', 'de', 'es', 'fi', 'fr', 'hu', 'it', 'ja', 'ko', 'nl', 'no', 'pl', 'pt', 'pt-br', 'ro', 'ru', 'sv', 'tr', 'zh-hans', 'zh-hant']

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

def get_namespace_from_title(db, title):
	namespaces_dict = db['metadata'].find_one({'key': 'namespaces'})['value']
	for namespace in namespaces_dict:
		if title.startswith(namespaces_dict[namespace] + ':'):
			return int(namespace)
	return 0

def load(wiki):
	db = connection[config['wikis'][wiki]['db_name']]
	w_api = wiki_api.Wiki_API(config['wikis'][wiki]['api_url'], config['wikis'][wiki]['username'], config['wikis'][wiki]['password'])
	print('Successfully loaded ' + wiki)
	return db, w_api

def get_user_id(db, wiki, w_api, username):
	user = db['users'].find_one({'username': username}, fields=[])
	if user is None:
		user = w_api.get_user_info(username)
		if 'registration' in user and user['registration'] is not None:
			registration = get_date_from_string(user['registration'])
		else:
			registration = None
		user_id = db['users'].insert({'username': username, 'registration': registration})
		cache.delete('wiki-fi:userlist_{0}'.format(wiki))
		cache.delete('wiki-fi:userwikislist_{0}'.format(username.replace(' ', '_')))
		cache.delete('wiki-fi:allusers')
	else:
		user_id = user['_id']

	return user_id

def get_page_id(db, wiki, title, ns, redirect):
	page = db['pages'].find_one({'title': title}, fields=[])
	if page is None:
		for lang in langArray:
			if title.endswith('/' + lang):
				language = lang
				break
		else:
			language = 'en'
		page_id = db['pages'].insert({'title': title, 'ns': ns, 'lang': language, 'redirect': redirect})
	else:
		page_id = page['_id']

	return page_id

def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0:
		return None
	return (db['edits'].find(fields=['timestamp'], sort=[('timestamp', pymongo.DESCENDING)]).limit(1))[0]['timestamp']

def seeder(wiki, db, w_api, namespace, namespace_name, pages, redirects, cutoff_date, lock):
	users = {}

	for page in pages:
		page_name = page['title'].encode('utf-8')
		page_id = get_page_id(db, wiki, page_name, namespace, redirects)
		revisions = w_api.get_page_revisions(page_name)

		print('Inserting edits for ' + page_name)
		first = True
		for revision in revisions:
			username = revision['user'].encode('utf-8')
			timestamp = get_date_from_string(revision['timestamp'])
			revid = revision['revid']

			if timestamp < cutoff_date:
				if username in users:
					user_id = users[username]
				else:
					lock.acquire()
					user_id = get_user_id(db, wiki, w_api, username)
					lock.release()
					users[username] = user_id

				output = {'user_id': user_id,
                          'ns': namespace,
                          'revid': revid,
                          'page_id': page_id,
                          'timestamp': timestamp,
                          'new_page': first
                          }
				db['edits'].insert(output)
				first = False

		if namespace == 6:
			uploads = w_api.get_file_uploads(page_name)
			if uploads is None:
				# it's a redirect page
				continue

			for upload in uploads:
				username = upload['user'].encode('utf-8')
				timestamp = get_date_from_string(upload['timestamp'])

				if timestamp < cutoff_date:
					if username in users:
						user_id = users[username]
					else:
						lock.acquire()
						user_id = get_user_id(db, wiki, w_api, username)
						lock.release()
						users[username] = user_id

					output = {'user_id': user_id,
	                          'page_id': page_id,
	                          'timestamp': timestamp
	                          }
					db['files'].insert(output)

	if not redirects:
		namespaces_dict = db['metadata'].find_one({'key': 'namespaces'})['value']
		namespaces_dict[str(namespace)] = namespace_name
		db['metadata'].update({'key': 'namespaces'}, {'$set': {'value': namespaces_dict}})

def seed(wiki):
	db, w_api = load(wiki)
	seedpool = threadpool.ThreadPool(2)
	lock = threading.Lock()

	cutoff_date = datetime.datetime.now()
	print('cutoff date for edits is: ' + str(cutoff_date))

	namespaces = w_api.get_all_namespaces()

	db['metadata'].update({'key': 'namespaces'}, {'$set': {'value': {}}}, upsert=True)

	for namespace in namespaces:
		# skip invalid namespace ids
		if int(namespace) < 0:
			continue

		# main namespace has no name
		if namespace == '0':
			namespace_name = 'Main'
		else:
			namespace_name = namespaces[namespace]['*']

		# better to store namespace id as int
		namespace = int(namespace)

		non_redirect_pages = w_api.get_all_pages(namespace, False)
		arglist = (wiki, db, w_api, namespace, namespace_name, non_redirect_pages, False, cutoff_date, lock)
		workrequest = threadpool.WorkRequest(seeder, arglist)
		seedpool.putRequest(workrequest)

		redirect_pages = w_api.get_all_pages(namespace, True)
		arglist = (wiki, db, w_api, namespace, namespace_name, redirect_pages, True, cutoff_date, lock)
		workrequest = threadpool.WorkRequest(seeder, arglist)
		seedpool.putRequest(workrequest)

	seedpool.wait()

	# update last_updated time
	db['metadata'].update({'key': 'user_and_pages_last_updated'}, {'$set': {'value': cutoff_date}}, upsert=True)
	cache.set('wiki-fi:user_and_pages_last_updated_' + wiki, cutoff_date, timeout=0)

def update(wiki):
	db, w_api = load(wiki)

	last_edit = get_last_edit_datetime(db)
	print('Last edit time was: ' + str(last_edit))

	print('Fetching edits from wiki...')
	recent_edits = w_api.get_recent_changes(last_edit)
	print('Successfully fetched edits from wiki')

	expensive_users_updated = []
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
		if 'user' in edit:
			username = edit['user'].encode('utf-8')
		if 'title' in edit:
			title = edit['title'].encode('utf-8')
		if 'ns' in edit:
			ns = edit['ns']
		if 'rcid' in edit:
			rcid = edit['rcid']
		if 'redirect' in edit:
			redirect = True
		else:
			redirect = False

		if edit['type'] == 'new':
			print('RCID: {0} - NEWPAGE: {1}'.format(rcid, title))

			user_id = get_user_id(db, wiki, w_api, username)
			page_id = get_page_id(db, wiki, title, ns, redirect)
			output = {'user_id': user_id,
                      'ns': ns,
                      'revid': edit['revid'],
                      'page_id': page_id,
                      'timestamp': timestamp,
                      'new_page': True
                      }
			db['edits'].insert(output)
			cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

		elif edit['type'] == 'edit':
			print('RCID: {0} - EDIT: {1}'.format(rcid, title))

			user_id = get_user_id(db, wiki, w_api, username)
			page_id = get_page_id(db, wiki, title, ns, redirect)
			output = {'user_id': user_id,
                      'ns': ns,
                      'revid': edit['revid'],
                      'page_id': page_id,
                      'timestamp': timestamp,
                      'new_page': False
                      }
			db['edits'].insert(output)
			db['pages'].update({'_id': page_id}, {'$set': {'redirect': redirect}})
			cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

		elif edit['type'] == 'log':
			if edit['logtype'] == 'move':
				if edit['logaction'] == 'move_redir':
					print('RCID: {0} - PAGEMOVE: {1} -> {2}'.format(rcid, title, edit['0'].encode('utf-8')))
				else:
					print('RCID: {0} - PAGEMOVE: {1} -> {2}'.format(rcid, title, edit['move']['new_title'].encode('utf-8')))

				page_id = get_page_id(db, wiki, title, ns, redirect)
				old_page_title = edit['title'].encode('utf-8')
				if edit['logaction'] == 'move_redir':
					new_page_title = edit['0'].encode('utf-8')
					# ugly hack because api doesn't return new namespace
					new_page_ns = get_namespace_from_title(db, new_page_title)
				else:
					new_page_title = edit['move']['new_title'].encode('utf-8')
					new_page_ns = edit['move']['new_ns']

				# delete existing target page and any edits that referenced it
				target_page = db['pages'].find_one({'title': new_page_title})
				if target_page:
					db['pages'].remove({'_id': target_page['_id']})
					db['edits'].remove({'page_id': target_page['_id']})

				for lang in langArray:
					if new_page_title.endswith('/' + lang):
						language = lang
						break
				else:
					language = 'en'
				# rename oldpage to newpage
				db['pages'].update({'_id': page_id}, {'$set': {'title': new_page_title, 'ns': new_page_ns, 'lang': language, 'redirect': False}})
				cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

				if 'suppressedredirect' in edit or ('move' in edit and 'suppressedredirect' not in edit['move']):
					# left behind a redirect
					print('RCID: {0} - REDIRECTCREATION: {1}'.format(rcid, title))

					page_id = get_page_id(db, wiki, title, ns, True)
					user_id = get_user_id(db, wiki, w_api, username)
					output = {'user_id': user_id,
                              'ns': ns,
                              'revid': edit['revid'],
                              'page_id': page_id,
                              'timestamp': timestamp,
                              'new_page': True
                              }
					db['edits'].insert(output)
					db['pages'].update({'_id': page_id}, {'$set': {'redirect': True}})
					cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

			elif edit['logtype'] == 'upload':
				print('RCID: {0} - FILEUPLOAD: {1}'.format(rcid, title))

				user_id = get_user_id(db, wiki, w_api, username)
				page_id = get_page_id(db, wiki, title, ns, redirect)

				output = {'user_id': user_id,
		                  'page_id': page_id,
		                  'timestamp': timestamp
		                  }
				db['files'].insert(output)

				if edit['logaction'] == 'upload':
					output = {'user_id': user_id,
	                          'ns': ns,
	                          'revid': edit['revid'],
	                          'page_id': page_id,
	                          'timestamp': timestamp,
	                          'new_page': True
	                          }
					db['edits'].insert(output)
					cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

			elif edit['logtype'] == 'delete':
				if edit['logaction'] == 'delete':
					print('RCID: {0} - DELETION: {1}'.format(rcid, title))

					page_id = get_page_id(db, wiki, edit['title'], ns, redirect)
					db['edits'].remove({'page_id': page_id})
					db['pages'].remove({'_id': page_id})
					db['files'].remove({'page_id': page_id})
					cache.delete('wiki-fi:pagedata_{0}_{1}'.format(title.replace(' ', '_'), wiki))

				elif edit['logaction'] == 'restore':
					print('RCID: {0} - RESTORE: {1}'.format(rcid, title))

					page_id = get_page_id(db, wiki, edit['title'], ns, redirect)
					revisions = w_api.get_page_revisions(edit['title'])

					first = True
					for revision in revisions:
						username = revision['user'].encode('utf-8')
						timestamp = get_date_from_string(revision['timestamp'])
						revid = revision['revid']

						user_id = get_user_id(db, wiki, w_api, username)

						output = {'user_id': user_id,
		                          'ns': ns,
		                          'revid': revid,
		                          'page_id': page_id,
		                          'timestamp': timestamp,
		                          'new_page': first
		                          }
						db['edits'].insert(output)
						first = False

					if ns == 6:
						uploads = w_api.get_file_uploads(edit['title'])
						if uploads is None:
							# it's a redirect page
							continue

						for upload in uploads:
							username = upload['user'].encode('utf-8')
							timestamp = get_date_from_string(upload['timestamp'])

							user_id = get_user_id(db, wiki, w_api, username)

							output = {'user_id': user_id,
			                          'page_id': page_id,
			                          'timestamp': timestamp
			                          }
							db['files'].insert(output)

			elif edit['logtype'] == 'newusers':
				print('RCID: {0} - NEWUSER: {1}'.format(rcid, username))

			elif edit['logtype'] == 'block':
				print('RCID: {0} - BLOCK: {1}'.format(rcid, title))

			else:
				print('MISSED')
				print edit
		else:
			print('MISSED')
			print edit

		last_seen_rcid = edit['rcid']

		if username not in config['wikis'][wiki]['expensive_users']:
			cache.delete('wiki-fi:userdata_{0}_{1}'.format(username.replace(' ', '_'), wiki))
		elif username not in expensive_users_updated:
			expensive_users_updated.append(username)

	# reanalyze expensive users
	print('Recaching results for expensive users...')
	for username in expensive_users_updated:
		charts_data = analyze.analyze_user(wiki, db, db['users'].find_one({'username': username}))
		cache.set('wiki-fi:userdata_{0}_{1}'.format(username.replace(' ', '_'), wiki), charts_data, timeout=0)

	# update last_updated time
	db['metadata'].update({'key': 'last_seen_rcid'}, {'$set': {'value': last_seen_rcid}}, upsert=True)
	db['metadata'].update({'key': 'user_and_pages_last_updated'}, {'$set': {'value': datenow}}, upsert=True)
	cache.set('wiki-fi:user_and_pages_last_updated_' + wiki, datenow, timeout=0)

	cache.delete('wiki-fi:wiki-fi_stats')

def update_wiki_data(wiki):
	db, w_api = load(wiki)

	print('Analyzing wiki...')
	charts_data = analyze.analyze_wiki(wiki, db)

	print('Caching results...')
	datenow = datetime.datetime.now()
	cache.set('wiki-data_{0}'.format(wiki), charts_data, timeout=0)
	db['metadata'].update({'key': 'wiki_last_updated'}, {'$set': {'value': datenow}}, upsert=True)
	cache.set('wiki-fi:wiki_last_updated_' + wiki, datenow, timeout=0)

def update_all():
	for wiki in config['wikis']:
		update(wiki)

def update_wiki_data_all():
	for wiki in config['wikis']:
		update_wiki_data(wiki)

if __name__ == '__main__':
	if sys.argv[1] == 'seed':
		seed(sys.argv[2])
	elif sys.argv[1] == 'update':
		update(sys.argv[2])
	elif sys.argv[1] == 'update_all':
		update_all()
	elif sys.argv[1] == 'update_wiki':
		update_wiki_data(sys.argv[2])
	elif sys.argv[1] == 'update_wiki_all':
		update_wiki_data_all()
