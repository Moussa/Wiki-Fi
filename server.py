import json
import pymongo
from flask import Flask, url_for, render_template, request, Response
import analyze
import wiki_api
from config import config

app = Flask(__name__)

connection = pymongo.Connection('localhost', 27017)

tfwikidb = connection[config['tfwiki']['db_name']]
portalwikidb = connection[config['portalwiki']['db_name']]
dota2wikidb = connection[config['dota2wiki']['db_name']]

wiki_mapping = {'tf': tfwikidb, 'portal': portalwikidb, 'dota2': dota2wikidb}

tfwikiapi = wiki_api.API(config['tfwiki']['api_url'], config['tfwiki']['username'], config['tfwiki']['password'])
portalwikiapi = wiki_api.API(config['portalwiki']['api_url'], config['portalwiki']['username'], config['portalwiki']['password'])
dota2wikiapi = wiki_api.API(config['dota2wiki']['api_url'], config['dota2wiki']['username'], config['dota2wiki']['password'])

api_mapping = {'tf': tfwikiapi, 'portal': portalwikiapi, 'dota2': dota2wikiapi}

@app.route('/is_valid_user', methods=['POST'])
def is_valid_user():
	username = request.form['username']
	wiki = request.form['wiki']
	user = wiki_mapping[wiki]['users'].find_one({'username': username})
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
	user = wiki_mapping[wiki]['users'].find_one({'username': username})

	# update user edits from wiki
	api_mapping[wiki].update_user_edits(wiki_mapping[wiki], user)

	charts_data = analyze.analyze_user(wiki_mapping[wiki], user)
	return render_template('stats.html', username=username, charts_data=charts_data)

# @app.route('/all', methods=['GET'])
# def analyze_all_edits():
# 	outputstring, piechart_output = analyze.analyze_all(db)
# 	return render_template('stats.html', edits=outputstring, username='Edits', piechart_output=piechart_output)

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
