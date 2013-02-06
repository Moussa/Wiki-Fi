import json
import pymongo
from flask import Flask, url_for, render_template, request, Response
import analyze
import wiki_api
from config import config

app = Flask(__name__)

connection = pymongo.Connection('localhost', 27017)

db = connection[config['db_name']]
userscollection = db['users']

api = wiki_api.API(config['api_url'], config['username'], config['password'])

@app.route('/is_user', methods=['POST'])
def is_user():
	username = request.form['username']
	user = userscollection.find_one({'username': username})
	data = {'user_exists': user is not None}
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

	return resp

@app.route('/')
def homepage():
	return render_template('form.html')

@app.route('/stats', methods=['GET'])
def anaylze_edits():
	if 'username' not in request.args:
		homepage()

	username = request.args['username']

	# update user edits from wiki
	api.update_user_edits(db, user)

	charts_data = analyze.analyze_user(db, user)
	return render_template('stats.html', username=username, charts_data=charts_data)

@app.route('/all', methods=['GET'])
def analyze_all_edits():
	outputstring, piechart_output = analyze.analyze_all(db)
	return render_template('stats.html', edits=outputstring, username='Edits', piechart_output=piechart_output)

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
