# -*- coding: utf-8 -*-
import json, re, datetime
import pymongo
import wikitools
from config import config

class API:
	def __init__(self, wiki_api_url, username, password):
		self.wiki = wikitools.Wiki(wiki_api_url)
		self.wiki.login(username=username, password=password)
		self.dateRE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z')

	def get_users(self, edited_only=False):
		params = {'action': 'query',
				  'list': 'allusers',
				  'aulimit': '5000',
				  'auprop': 'registration'
				  }

		if edited_only:
			params['auwitheditsonly'] = ''

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		return res['query']['allusers']

	def get_user_edits(self, user, start=None):
		params = {'action': 'query',
				  'list': 'usercontribs',
				  'ucuser': user,
				  'uclimit': '5000'
				  }

		if start:
			params['ucend'] = start
			params['ucstart'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		return res['query']['usercontribs']

	def update_users(self, db):
		users = self.get_users()
		for user in users:
			username = user['name']
			tfwiki_registration = user['registration']
			res = self.dateRE.search(tfwiki_registration)
			year = int(res.group(1))
			month = int(res.group(2))
			day = int(res.group(3))
			hour = int(res.group(4))
			minute = int(res.group(5))
			second = int(res.group(6))
			d = datetime.datetime(year, month, day, hour, minute, second)
			if db['users'].find_one({'username': username}) is None:
				db['users'].insert({'username': username, 'registration': d}, safe=True)
			elif 'registration' not in db['users'].find_one({'username': username}):
				db['users'].update({'username': username}, {'registration': d})

	def update_user_edits(self, db, user):
		if db['edits'].find({'user_id': user['_id']}).count() == 0:
			edits = self.get_user_edits(user['username'])
		else:
			last_edit_date = (db['edits'].find({'user_id': user['_id']}, sort=[('date', pymongo.DESCENDING )]).limit(1))[0]['timestamp']
			edits = self.get_user_edits(user['username'], last_edit_date)
			edits = edits[:-1]  # remove last duplicate edit

		for edit in edits:
			res = self.dateRE.search(edit['timestamp'])
			year = int(res.group(1))
			month = int(res.group(2))
			day = int(res.group(3))
			hour = int(res.group(4))
			minute = int(res.group(5))
			second = int(res.group(6))
			d = datetime.datetime(year, month, day, hour, minute, second)
			date_index_string = '{0}-{1}-{2}'.format(year, month, day)
			output = {'user_id': user['_id'],
					  'ns': edit['ns'],
					  'revid': edit['revid'],
					  'date': d,
					  'title': edit['title'],
					  'date_string': date_index_string,
					  'timestamp': edit['timestamp'],
					  'comment': edit['comment']
					  }
			db['edits'].insert(output, safe=True)