# -*- coding: utf-8 -*-
import json
import pymongo
from flask import Flask, url_for, render_template, request, Response
import analyze
from config import config
from werkzeug.contrib.cache import MemcachedCache

app = Flask(__name__)
cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.Connection(config['db']['host'], config['db']['port'])

wiki_dict = {}
for wiki in config['wikis']:
	db = connection[config['wikis'][wiki]['db_name']]
	print('Successfully loaded ' + wiki)
	wiki_dict[wiki] = db


def get_chart_data(wiki, db, user):
	charts_data = cache.get('wiki-data_{0}_{1}'.format(user['username'].replace(' ', '_'), wiki))
	if charts_data is None:
		charts_data = analyze.analyze_user(wiki, db, user)
		cache.set('wiki-data_{0}_{1}'.format(user['username'].replace(' ', '_'), wiki), charts_data, timeout=0)
	return charts_data

@app.route('/is_valid_user', methods=['POST'])
def is_valid_user():
	username = request.form['username']
	wiki = request.form['wiki']
	wikiuserlist = cache.get('wiki-data_userlist_{0}'.format(wiki))
	if wikiuserlist is None:
		wikiuserlist = [user['username'] for user in wiki_dict[wiki]['users'].find()]
		cache.set('wiki-data_userlist_{0}'.format(wiki), wikiuserlist, timeout=0)
	data = username in wikiuserlist
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

	return resp

@app.route('/get_all_users', methods=['GET'])
def get_all_users():
	users = cache.get('wiki-data_allusers')
	if users is None:
		users = []
		for wiki in config['wikis']:
			users += [user['username'] for user in list(wiki_dict[wiki]['users'].find())]
		users = list(set(users))
		cache.set('wiki-data_allusers', users, timeout=0)
	resp = Response(json.dumps(users), status=200, mimetype='application/json')

	return resp

@app.route('/get_wiki_users', methods=['POST'])
def get_wiki_users():
	wiki = request.form['wiki']
	wikiuserlist = cache.get('wiki-data_userlist_{0}'.format(wiki))
	if wikiuserlist is None:
		wikiuserlist = [user['username'] for user in wiki_dict[wiki]['users'].find()]
		cache.set('wiki-data_userlist_{0}'.format(wiki), wikiuserlist, timeout=0)
	resp = Response(json.dumps(wikiuserlist), status=200, mimetype='application/json')

	return resp

@app.route('/get_user_wikis', methods=['POST'])
def get_user_wikis():
	username = request.form['username']
	userwikislist = cache.get('wiki-data_userwikislist_{0}'.format(username))
	if userwikislist is None:
		userwikislist = []
		for wiki in wiki_dict:
			if wiki_dict[wiki]['users'].find_one({'username': username}):
				userwikislist.append(wiki)
		cache.set('wiki-data_userwikislist_{0}'.format(username), userwikislist, timeout=0)
	resp = Response(json.dumps(userwikislist), status=200, mimetype='application/json')

	return resp

@app.route('/get_last_updated', methods=['POST'])
def get_last_updated():
	wiki = request.form['wiki']
	last_updated = cache.get('wiki-metadata_last_updated_' + wiki)
	if last_updated is None:
		last_updated = (wiki_dict[wiki]['metadata'].find_one({'key': 'last_updated'}))['last_updated']
		cache.set('wiki-metadata_last_updated_' + wiki, last_updated, timeout=0)
	last_updated = last_updated.strftime("%H:%M, %d %B %Y (UTC)")
	resp = Response(json.dumps(last_updated), status=200, mimetype='application/json')

	return resp

@app.route('/')
def homepage():
	return render_template('form.html')

def invalid_args():
	return render_template('form.html', error=True)

@app.route('/stats', methods=['GET'])
def anaylze_edits():
	if 'username' not in request.args or 'wiki' not in request.args or request.args['wiki'] not in wiki_dict:
		return invalid_args()

	username = request.args['username']
	wiki = request.args['wiki']
	user = wiki_dict[wiki]['users'].find_one({'username': username})
	if user is None:
		return invalid_args()
	wiki_link = config['wikis'][wiki]['wiki_link']

	charts_data = get_chart_data(wiki, wiki_dict[wiki], user)

	return render_template('stats.html', username=username, wiki=wiki, wiki_link=wiki_link, charts_data=charts_data)

if __name__ == '__main__':
	app.run(debug=False, host='0.0.0.0', port=5000)
