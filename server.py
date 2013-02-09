import json
import pymongo
from flask import Flask, url_for, render_template, request, Response
import analyze
import wiki_api
from config import config

app = Flask(__name__)

connection = pymongo.Connection('localhost', 27017)

wiki_dict = {}
for wiki in config:
	db = connection[config[wiki]['db_name']]
	api = wiki_api.API(config[wiki]['api_url'], config[wiki]['username'], config[wiki]['password'])
	print('Successfully loaded ' + wiki)
	wiki_dict[wiki] = {'db': db, 'api': api}

@app.route('/is_valid_user', methods=['POST'])
def is_valid_user():
	username = request.form['username']
	wiki = request.form['wiki']
	user = wiki_dict[wiki]['db']['users'].find_one({'username': username})
	data = user is not None
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

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

	charts_data = analyze.analyze_user(wiki, wiki_dict[wiki]['db'], user)
	return render_template('stats.html', username=username, wiki=wiki, charts_data=charts_data)

# @app.route('/all', methods=['GET'])
# def analyze_all_edits():
# 	outputstring, piechart_output = analyze.analyze_all(db)
# 	return render_template('stats.html', edits=outputstring, username='Edits', piechart_output=piechart_output)

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
