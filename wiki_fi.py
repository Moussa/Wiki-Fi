# -*- coding: utf-8 -*-
import json, locale
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


def get_user_chart_data(wiki, db, user):
	charts_data = cache.get('wiki-fi:userdata_{0}_{1}'.format(user['username'].replace(' ', '_'), wiki))
	if charts_data is None:
		charts_data = analyze.analyze_user(wiki, db, user)
		cache.set('wiki-fi:userdata_{0}_{1}'.format(user['username'].replace(' ', '_'), wiki), charts_data, timeout=0)
	return charts_data

def get_page_chart_data(wiki, db, page):
	charts_data = cache.get('wiki-fi:pagedata_{0}_{1}'.format(page['title'].replace(' ', '_'), wiki))
	if charts_data is None:
		charts_data = analyze.analyze_page(wiki, db, page)
		cache.set('wiki-fi:pagedata_{0}_{1}'.format(page['title'].replace(' ', '_'), wiki), charts_data, timeout=0)
	return charts_data

def get_wiki_chart_data(wiki, db):
	charts_data = cache.get('wiki-data_{0}'.format(wiki))
	if charts_data is None:
		charts_data = analyze.analyze_wiki(wiki, db)
		cache.set('wiki-data_{0}'.format(wiki), charts_data, timeout=0)
	return charts_data

def get_wiki_fi_stats():
	stats = cache.get('wiki-fi:wiki-fi_stats')
	if stats is None:
		stats = {'no_of_users': 0, 'no_of_edits': 0, 'no_of_pages': 0}
		for wiki in wiki_dict:
			stats['no_of_users'] += wiki_dict[wiki]['users'].count()
			stats['no_of_edits'] += wiki_dict[wiki]['edits'].count()
			stats['no_of_pages'] += wiki_dict[wiki]['pages'].count()
		locale.setlocale(locale.LC_ALL, 'en_US.utf8')
		for stat in stats:
			stats[stat] = locale.format("%d", stats[stat], grouping=True)
		cache.set('wiki-fi:wiki-fi_stats', stats, timeout=0)
	return stats

@app.route('/is_valid_user', methods=['POST'])
def is_valid_user():
	username = request.form['username'].replace('_', ' ')
	wiki = request.form['wiki']
	wikiuserlist = cache.get('wiki-fi:userlist_{0}'.format(wiki))
	if wikiuserlist is None:
		wikiuserlist = [user['username'] for user in wiki_dict[wiki]['users'].find(fields=['username'])]
		cache.set('wiki-fi:userlist_{0}'.format(wiki), wikiuserlist, timeout=0)
	data = username in wikiuserlist
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

	return resp

@app.route('/is_valid_page', methods=['POST'])
def is_valid_page():
	page = request.form['page'].replace('_', ' ')
	wiki = request.form['wiki']
	page_info = wiki_dict[wiki]['pages'].find_one({'title': page}, fields=['title'])
	data = page_info is not None
	resp = Response(json.dumps(data), status=200, mimetype='application/json')

	return resp

@app.route('/get_wiki_users', methods=['POST'])
def get_wiki_users():
	wiki = request.form['wiki']
	wikiuserlist = cache.get('wiki-fi:userlist_{0}'.format(wiki))
	if wikiuserlist is None:
		wikiuserlist = [user['username'] for user in wiki_dict[wiki]['users'].find(fields=['username'])]
		cache.set('wiki-fi:userlist_{0}'.format(wiki), wikiuserlist, timeout=0)
	resp = Response(json.dumps(wikiuserlist), status=200, mimetype='application/json')

	return resp

@app.route('/get_wiki_pages', methods=['POST'])
def get_wiki_pages():
	wiki = request.form['wiki']
	wikipagelist = cache.get('wiki-fi:pagelist_{0}'.format(wiki))
	if wikipagelist is None:
		wikipagelist = [page['title'] for page in wiki_dict[wiki]['pages'].find({'ns': {'$in': [0, 4, 8]}, 'lang': 'en', 'redirect': False}, fields=['title'])]
		cache.set('wiki-fi:pagelist_{0}'.format(wiki), wikipagelist, timeout=0)
	resp = Response(json.dumps(wikipagelist), status=200, mimetype='application/json')

	return resp

@app.route('/get_user_wikis', methods=['POST'])
def get_user_wikis():
	username = request.form['username'].replace('_', ' ')
	userwikislist = cache.get('wiki-fi:userwikislist_{0}'.format(username.replace(' ', '_')))
	if userwikislist is None:
		userwikislist = []
		for wiki in wiki_dict:
			if wiki_dict[wiki]['users'].find_one({'username': username}, fields=[]):
				userwikislist.append(wiki)
		cache.set('wiki-fi:userwikislist_{0}'.format(username.replace(' ', '_')), userwikislist, timeout=0)
	resp = Response(json.dumps(userwikislist), status=200, mimetype='application/json')

	return resp

@app.route('/get_page_wikis', methods=['POST'])
def get_page_wikis():
	page = request.form['page'].replace('_', ' ')
	pagewikislist = cache.get('wiki-fi:pagewikislist_{0}'.format(page.replace(' ', '_')))
	if pagewikislist is None:
		pagewikislist = []
		for wiki in wiki_dict:
			if wiki_dict[wiki]['pages'].find_one({'title': page}, fields=[]):
				pagewikislist.append(wiki)
		cache.set('wiki-fi:userwikislist_{0}'.format(page.replace(' ', '_')), pagewikislist, timeout=0)
	resp = Response(json.dumps(pagewikislist), status=200, mimetype='application/json')

	return resp

@app.route('/get_last_updated', methods=['POST'])
def get_last_updated():
	wiki = request.form['wiki']
	last_updated = cache.get('wiki-fi:user_and_pages_last_updated_' + wiki)
	if last_updated is None:
		last_updated = (wiki_dict[wiki]['metadata'].find_one({'key': 'user_and_pages_last_updated'}, fields=['value']))['value']
		cache.set('wiki-fi:user_and_pages_last_updated_' + wiki, last_updated, timeout=0)
	last_updated = last_updated.strftime("%H:%M, %d %B %Y (UTC)")
	resp = Response(json.dumps(last_updated), status=200, mimetype='application/json')

	return resp

@app.route('/get_wiki_last_updated', methods=['POST'])
def get_wiki_last_updated():
	wiki = request.form['wiki']
	last_updated = cache.get('wiki-fi:wiki_last_updated_' + wiki)
	if last_updated is None:
		last_updated = (wiki_dict[wiki]['metadata'].find_one({'key': 'wiki_last_updated'}, fields=['value']))['value']
		cache.set('wiki-fi:wiki_last_updated_' + wiki, last_updated, timeout=0)
	last_updated = last_updated.strftime("%H:%M, %d %B %Y (UTC)")
	resp = Response(json.dumps(last_updated), status=200, mimetype='application/json')

	return resp

@app.route('/')
def homepage(error=None):
	stats = get_wiki_fi_stats()
	return render_template('form.html', stats=stats, error=error)

@app.route('/about')
def about():
	return render_template('about.html')

@app.route('/user/<wiki>/<username>')
def anaylze_user(wiki, username):
	username = username.replace('_', ' ')
	user = wiki_dict[wiki]['users'].find_one({'username': username})
	if user is None:
		return homepage(error="invalid username")
	wiki_link = config['wikis'][wiki]['wiki_link']

	charts_data = get_user_chart_data(wiki, wiki_dict[wiki], user)

	return render_template('user_stats.html', username=username, wiki=wiki, wiki_link=wiki_link, charts_data=charts_data)

@app.route('/page/<wiki>/<path:pagetitle>')
def anaylze_page(wiki, pagetitle):
	pagetitle = pagetitle.replace('_', ' ')
	page = wiki_dict[wiki]['pages'].find_one({'title': pagetitle})
	if page is None:
		return homepage('invalid page')
	wiki_link = config['wikis'][wiki]['wiki_link']

	charts_data = get_page_chart_data(wiki, wiki_dict[wiki], page)

	return render_template('page_stats.html', page_name=page['title'], wiki=wiki, wiki_link=wiki_link, charts_data=charts_data)

@app.route('/wiki/<wiki>')
def anaylze_wiki(wiki):
	if wiki not in config['wikis']:
		return homepage('invalid wiki')
	wiki_link = config['wikis'][wiki]['wiki_link']
	charts_data = get_wiki_chart_data(wiki, wiki_dict[wiki])

	return render_template('wiki_stats.html', wiki_name=config['wikis'][wiki]['wiki_name'], wiki=wiki, wiki_link=wiki_link, charts_data=charts_data)

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
