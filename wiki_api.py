# -*- coding: utf-8 -*-
import re, datetime
import pymongo
import wikitools

class Wiki_API:
	def __init__(self, wiki_api_url, username, password):
		self.wiki = wikitools.Wiki(wiki_api_url)
		self.wiki.login(username=username, password=password)

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

	def get_recent_changes(self, start=None):
		params = {'action': 'query',
                  'list': 'recentchanges',
                  'rcprop': 'user|timestamp|title|ids',
                  'rctype': 'edit|new',
                  'rcdir': 'newer',
                  'rclimit': '5000'
                  }

		if start:
			params['rcstart'] = start

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		return res['query']['recentchanges']
