# -*- coding: utf-8 -*-
import re, datetime
import pymongo
import wikitools

class Wiki_API:
	def __init__(self, wiki_api_url, username, password):
		self.wiki = wikitools.Wiki(wiki_api_url)
		self.wiki.login(username=username, password=password)

	def get_all_namespaces(self):
		params = {'action': 'query',
                  'meta': 'siteinfo',
                  'siprop': 'namespaces'
                  }

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query()

		return res['query']['namespaces']

	def get_all_pages(self, namespace, redirects):
		params = {'action': 'query',
                  'list': 'allpages',
                  'aplimit': '5000',
                  'apnamespace': namespace,
                  'rawcontinue': ''
                  }

		if redirects:
			params['apfilterredir'] = 'redirects'
		else:
			params['apfilterredir'] = 'nonredirects'

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		return res['query']['allpages']

	def get_user_info(self, username):
		params = {'action': 'query',
                  'list': 'users',
                  'ususers': username,
                  'usprop': 'registration'
                  }

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query()

		return res['query']['users'][0]

	def get_page_revisions(self, page):
		params = {'action': 'query',
                  'prop': 'revisions',
                  'rvlimit': '5000',
                  'titles': page,
                  'rvprop': 'ids|timestamp|user',
                  'rvdir': 'newer',
                  'rawcontinue': ''
                  }

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		page_id = res['query']['pages'].keys()[0]
		return res['query']['pages'][page_id]['revisions']

	def get_file_uploads(self, _file):
		params = {'action': 'query',
                  'prop': 'imageinfo',
                  'iilimit': '5000',
                  'titles': _file,
                  'iiprop': 'timestamp|user',
                  'rawcontinue': ''
                  }

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		page_id = res['query']['pages'].keys()[0]
		if 'imageinfo' in res['query']['pages'][page_id]:
			return res['query']['pages'][page_id]['imageinfo']
		else:
			return None

	def get_recent_changes(self, start=None):
		params = {'action': 'query',
                  'list': 'recentchanges',
                  'rcprop': 'user|timestamp|title|ids|loginfo|redirect',
                  'rctype': 'edit|new|log',
                  'rcdir': 'newer',
                  'rclimit': '5000',
                  'rawcontinue': ''
                  }

		if start:
			params['rcstart'] = start

		req = wikitools.api.APIRequest(self.wiki, params)
		res = req.query(querycontinue=True)

		return res['query']['recentchanges']
