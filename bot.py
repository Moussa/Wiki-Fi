import json
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


def get_last_edit_datetime(db):
	if db['edits'].find().count() == 0
		return None
	return (db['edits'].find({}, sort=[('date', pymongo.DESCENDING )]).limit(1))[0]['timestamp']

def insert_recent_edits():
	for wiki in wiki_dict:
		db = wiki_dict[wiki]['db']
		api = wiki_dict[wiki]['api']

		last_edit = get_last_edit_datetime(db)
		recent_edits = api.get_recent_changes(last_edit)
		recent_edits = recent_edits[:-1]  # remove last duplicate edit


if __name__ == '__main__':
	insert_recent_edits()