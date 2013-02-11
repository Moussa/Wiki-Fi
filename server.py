import json
import pymongo
from flask import Flask, url_for, render_template, request, Response
import analyze
import wiki_api
from config import config
from werkzeug.contrib.cache import MemcachedCache

app = Flask(__name__)
cache = MemcachedCache(['{0}:{1}'.format(config['memcached']['host'], config['memcached']['port'])])
connection = pymongo.Connection(config['db']['host'], config['db']['port'])

wiki_dict = {}
for wiki in config['wikis']:
	db = connection[config['wikis'][wiki]['db_name']]
	api = wiki_api.API(config['wikis'][wiki]['api_url'], config['wikis'][wiki]['username'], config['wikis'][wiki]['password'])
	print('Successfully loaded ' + wiki)
	wiki_dict[wiki] = {'db': db, 'api': api}


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
	user = wiki_dict[wiki]['db']['users'].find_one({'username': username})
	data = user is not None
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

	return resp

@app.route('/get_all_users', methods=['GET'])
def get_all_users():
	users = cache.get('wiki-data_allusers')
	if users is None:
		users = []
		for wiki in config['wikis']:
			users += [user['username'] for user in list(wiki_dict[wiki]['db']['users'].find())]
		users = list(set(users))
		cache.set('wiki-data_allusers', users, timeout=0)
	resp = Response(json.dumps(users), status=200, mimetype='application/json')

	return resp

@app.route('/get_last_updated', methods=['POST'])
def get_last_updated():
	wiki = request.form['wiki']
	last_updated = cache.get('wiki-metadata_last_updated_' + wiki)
	if last_updated is None:
		last_updated = (wiki_dict[wiki]['db']['metadata'].find_one({'key': 'last_updated'}))['last_updated']
		cache.set('wiki-metadata_last_updated_' + wiki, last_updated, timeout=0)
	last_updated = last_updated.strftime("%H:%M, %d %B %Y")
	resp = Response(json.dumps(last_updated), status=200, mimetype='application/json')

	return resp

@app.route('/')
def homepage():
	return render_template('form.html')

@app.route('/stats', methods=['GET'])
def anaylze_edits():
	if 'username' or 'wiki' not in request.args:
		homepage()

	username = request.args['username']
	wiki = request.args['wiki']
	user = wiki_dict[wiki]['db']['users'].find_one({'username': username})

	charts_data = get_chart_data(wiki, wiki_dict[wiki]['db'], user)

	return render_template('stats.html', username=username, wiki=wiki, charts_data=charts_data)

# @app.route('/all', methods=['GET'])
# def analyze_all_edits():
# 	outputstring, piechart_output = analyze.analyze_all(db)
# 	return render_template('stats.html', edits=outputstring, username='Edits', piechart_output=piechart_output)

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
