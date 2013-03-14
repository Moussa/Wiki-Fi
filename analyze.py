# -*- coding: utf-8 -*-
import datetime, copy, json, locale, re, operator
import pymongo
from config import config
try:
	from collections import Counter
except:
	from counter import Counter

DAY_MAPPING = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
LANG_ARRAY = ['ar', 'cs', 'da', 'de', 'en', 'es', 'fi', 'fr', 'hu', 'it', 'ja', 'ko', 'nl', 'no', 'pl', 'pt', 'pt-br', 'ro', 'ru', 'sv', 'tr', 'zh-hans', 'zh-hant']

creationDateRE = re.compile(r'(\d{2})/(\d{2})/(\d{4})')

def get_creation_datetime_from_string(creation_date):
	res = creationDateRE.search(creation_date)
	day = int(res.group(1))
	month = int(res.group(2))
	year = int(res.group(3))

	return datetime.datetime(year, month, day)

def daterange(start_date, end_date):
	for n in range(int((end_date - start_date).days) + 1):
		yield start_date + datetime.timedelta(days=n)

def weeklydaterange(start_date, end_date):
	for n in range(0, int((end_date - start_date).days) + 1, 7):
		yield start_date + datetime.timedelta(days=n)

def get_user_registration_date(wiki, db, user=None, _id=None):
	if _id:
		registration_date = db['users'].find_one(_id)['registration']
	else:
		registration_date = db['users'].find_one(user['_id'])['registration']
	# some users have no registration date for whatever reason
	if registration_date is None:
		# use wiki creation date instead
		registration_date = get_creation_datetime_from_string(config['wikis'][wiki]['creation_date'])

	return registration_date

def get_page_name(db, _id):
	page = db['pages'].find_one(_id, fields=['title'])

	return page['title'].encode('utf-8')

def get_user_name(db, _id):
	user = db['users'].find_one(_id, fields=['username'])

	return user['username'].encode('utf-8')

def process_day_column_chart(edits_dict):
	day_output = []
	for day, day_entry in edits_dict.iteritems():
		day_output.append('[\'%s\', %s]' % (day_entry['day']['string'], day_entry['day']['count']))
	day_output = ",\n".join(day_output)

	return day_output

def process_hour_column_chart(edits_dict):
	hour_output = []
	for hour in range(0, 24):
		hour_total = 0
		for day in edits_dict:
			hour_total += edits_dict[day]['hours'][hour]['count']
		hour_output.append('[\'%s\', %s]' % ('%s:00' % ("%02d" % (hour,)), hour_total))
	hour_output = ',\n'.join(hour_output)

	return hour_output

def process_hour_day_bubble_chart(edits_dict):
	day_hour_output = []
	for day, day_entry in edits_dict.iteritems():
		for hour, entry in day_entry['hours'].iteritems():
			day_hour_output.append('[\'%s\', %s, %s, \'\', %s]' % (day_entry['day']['string'], hour, day+1, entry['count']))
	day_hour_output = ',\n'.join(day_hour_output)

	return day_hour_output

def process_language_pie_chart(wiki, db, pages_collection):
	language_piechart_output = []
	for lang in LANG_ARRAY:
		count = pages_collection.find({'ns': {'$in': [0, 4, 8]}, 'lang': lang}, fields=[]).count()
		if count > 0:
			language_piechart_output.append('[\'{0}\', {1}]'.format(lang, count))
	language_piechart_output = ',\n'.join(language_piechart_output)

	return language_piechart_output

def process_language_edits_pie_chart(wiki, db, pages_collection, edits_collection):
	language_edits_piechart_output = []
	for lang in LANG_ARRAY:
		count = 0
		for page in pages_collection.find({'ns': {'$in': [0, 4, 8]}, 'lang': lang}, fields=['_id']):
			count += edits_collection.find({'page_id': page['_id']}, fields=[]).count()
		if count > 0:
			language_edits_piechart_output.append('[\'{0}\', {1}]'.format(lang, count))
	language_edits_piechart_output = ',\n'.join(language_edits_piechart_output)

	return language_edits_piechart_output

def process_namespace_unique_pie_chart(wiki, db, edits_collection, user):
	namespace_mapping = db['metadata'].find_one({'key': 'namespaces'})['value']
	namespace_unique_piechart_output = []
	for namespace in namespace_mapping:
		count = len(edits_collection.find({'ns': int(namespace), 'user_id': user['_id']}, fields=[]).distinct('page_id'))
		if count > 0:
			namespace_unique_piechart_output.append('[\'{0}\', {1}]'.format(namespace_mapping[namespace], count))
	namespace_unique_piechart_output = ',\n'.join(namespace_unique_piechart_output)

	return namespace_unique_piechart_output

def process_namespace_pie_chart(wiki, db, edits_collection, user=None):
	namespace_mapping = db['metadata'].find_one({'key': 'namespaces'})['value']
	namespace_piechart_output = []
	for namespace in namespace_mapping:
		if user:
			count = edits_collection.find({'ns': int(namespace), 'user_id': user['_id']}, fields=[]).count()
		else:
			count = edits_collection.find({'ns': int(namespace)}, fields=[]).count()
		if count > 0:
			namespace_piechart_output.append('[\'{0}\', {1}]'.format(namespace_mapping[namespace], count))
	namespace_piechart_output = ',\n'.join(namespace_piechart_output)

	return namespace_piechart_output

def process_namespace_distribution_pie_chart(wiki, db, edits_collection):
	namespace_mapping = db['metadata'].find_one({'key': 'namespaces'})['value']
	namespace_distribution_piechart_output = []
	for namespace in namespace_mapping:
		count = len(edits_collection.find({'ns': int(namespace)}, fields=[]).distinct('page_id'))
		if count > 0:
			namespace_distribution_piechart_output.append('[\'{0}\', {1}]'.format(namespace_mapping[namespace], count))
	namespace_distribution_piechart_output = ',\n'.join(namespace_distribution_piechart_output)

	return namespace_distribution_piechart_output

def process_most_edited_pages(wiki, db, page_ids):
	most_edited = Counter(page_ids).most_common(100)
	output = []
	for entry in most_edited:
		page_title = get_page_name(db, entry[0])
		count = entry[1]
		json_entry = {}
		json_entry['text'] = '{0} ({1})'.format(page_title, count)
		json_entry['weight'] = count
		json_entry['link'] = {'href': '/page/{0}/{1}'.format(wiki, page_title.replace(' ', '_')), 'title': 'See stats for ' + page_title}
		output.append(json_entry)

	return json.dumps(output).replace(r"'", r"\'")

def process_most_frequent_editors(wiki, db, user_ids):
	most_edited = Counter(user_ids).most_common(50)
	output = []
	for entry in most_edited:
		username = get_user_name(db, entry[0])
		count = entry[1]
		json_entry = {}
		json_entry['text'] = '{0} ({1})'.format(username, count)
		json_entry['weight'] = count
		json_entry['link'] = {'href': '/user/{0}/{1}'.format(wiki, username.replace(' ', '_')), 'title': 'See stats for User:' + username}
		output.append(json_entry)

	return json.dumps(output).replace(r"'", r"\'")

def process_top_editors(wiki, db, user_edits_count):
	sorted_user_edits_count = sorted(user_edits_count.iteritems(), key=operator.itemgetter(1), reverse=True)[:100]
	output = []
	for entry in sorted_user_edits_count:
		username = get_user_name(db, entry[0])
		edit_count = entry[1]
		registration_date = get_user_registration_date(wiki, db, _id=entry[0])
		registered_days_ago = (datetime.datetime.today() - registration_date).days
		edit_count_per_day = "%0.2f" % (float(edit_count)/float(registered_days_ago),)
		output.append(["""<a href="/user/{0}/{1}">{1}</a>""".format(wiki, username), registration_date.strftime("%d %B %Y"), edit_count, edit_count_per_day])

	return output

def analyze_user(wiki, db, user):
	edits_collection = db['edits']
	pages_collection = db['pages']

	start_date = get_user_registration_date(wiki, db, user)
	end_date = datetime.datetime.today()

	edits_timeline = []
	page_ids = []
	largest_day_edit_count = 0
	longest_edit_days_streak = 0
	current_edit_days_streak = 0
	total_edit_count = 0
	last_30_days_edits = 0
	last_30_days_active_days = 0
	active_days = 0
	hour_dict = dict((a, {'count': 0, 'string': '{0}:00'.format("%02d" % (a,))}) for a in range(0, 24))
	edits_dict = dict((a, {'day': {'string': DAY_MAPPING[a], 'count': 0}, 'hours': copy.deepcopy(hour_dict)}) for a in range(0, 7))

	for single_date in daterange(start_date, end_date):
		start = datetime.datetime(single_date.year, single_date.month, single_date.day)
		end = start + datetime.timedelta(days=1)
		edits = list(edits_collection.find({'user_id': user['_id'], 'timestamp': {'$gte': start, '$lt': end}}, fields=['timestamp', 'page_id']))

		day_edit_count = len(edits)
		total_edit_count += day_edit_count

		# Keep track of activity in last 30 days
		if (datetime.datetime.today() - single_date).days < 30:
			last_30_days_edits += day_edit_count
			if day_edit_count > 0:
				last_30_days_active_days += 1

		# Keep track of largest edit counts in a day
		if day_edit_count > largest_day_edit_count:
			largest_day_edit_count = day_edit_count

		# Keep track of edit days streak
		if day_edit_count > 0:
			current_edit_days_streak += 1
			if current_edit_days_streak > longest_edit_days_streak:
				longest_edit_days_streak = current_edit_days_streak
			active_days += 1
		else:
			current_edit_days_streak = 0

		for edit in edits:
			page_ids.append(edit['page_id'])

			# Add hourly edits data to dict
			edit_hour = edit['timestamp'].hour
			edit_day = edit['timestamp'].weekday()
			edits_dict[edit_day]['hours'][edit_hour]['count'] += 1
			edits_dict[edit_day]['day']['count'] += 1

		entry = """[new Date({year}, {month}, {day}), {edits}, {total_edits}]"""
		
		editentry = entry.format(year=single_date.year,
                                 month=single_date.month-1,
                                 day=single_date.day,
                                 edits=day_edit_count,
                                 total_edits=total_edit_count
                                 )

		edits_timeline.append(editentry)

	distinct_pages_count = len(edits_collection.find({'user_id': user['_id']}, fields=[]).distinct('page_id'))

	pages_created = edits_collection.find({'user_id': user['_id'], 'new_page': True}, fields=[]).count()

	files_uploaded = db['files'].find({'user_id': user['_id']}, fields=[]).count()

	days_since_registration = (datetime.datetime.today() - start_date).days

	time_period = (end_date - start_date).days + 1
	edits_per_day = '%.2f' % (float(total_edit_count)/float(time_period))
	activity_percentage = '%.2f' % (100 * float(active_days)/float(time_period))
	edits_per_day_30days = '%.2f' % (float(last_30_days_edits)/30.0)
	activity_percentage_30days = '%.2f' % (100 * float(last_30_days_active_days)/30.0)

	start_date = start_date.strftime("%d %B %Y")
	end_date = end_date.strftime("%d %B %Y")

	# Format numbers with separators
	locale.setlocale(locale.LC_ALL, 'en_US.utf8')
	total_edit_count = locale.format("%d", total_edit_count, grouping=True)
	distinct_pages_count = locale.format("%d", distinct_pages_count, grouping=True)
	days_since_registration = locale.format("%d", days_since_registration, grouping=True)
	longest_edit_days_streak = locale.format("%d", longest_edit_days_streak, grouping=True)
	current_edit_days_streak = locale.format("%d", current_edit_days_streak, grouping=True)
	largest_day_edit_count = locale.format("%d", largest_day_edit_count, grouping=True)
	pages_created = locale.format("%d", pages_created, grouping=True)
	files_uploaded = locale.format("%d", files_uploaded, grouping=True)

	# Generate list of most edited pages
	most_edited_pages = process_most_edited_pages(wiki, db, page_ids)

	# Generate data table string for day/hour bubble chart
	hour_day_bubble_chart_string = process_hour_day_bubble_chart(edits_dict)

	# Generate data table string for hour column chart
	hour_column_chart_string = process_hour_column_chart(edits_dict)

	# Generate data table string for day column chart
	day_column_chart_string = process_day_column_chart(edits_dict)

	# Generate data table string for namespace pie chart
	namespace_piechart_string = process_namespace_pie_chart(wiki, db, edits_collection, user)

	# Generate data table string for language edits distribution pie chart
	namespace_unique_piechart_string  = process_namespace_unique_pie_chart(wiki, db, edits_collection, user)

	# Generate data table string for edits timeline chart
	edits_timeline_string = ',\n'.join(sorted(edits_timeline))

	charts_data = {'start_date': start_date,
	               'total_edit_count': total_edit_count,
                   'distinct_pages_count': distinct_pages_count,
                   'pages_created': pages_created,
                   'files_uploaded': files_uploaded,
                   'days_since_registration': days_since_registration,
                   'edits_per_day': edits_per_day,
                   'activity_percentage': activity_percentage,
                   'edits_per_day_30days': edits_per_day_30days,
                   'activity_percentage_30days': activity_percentage_30days,
                   'longest_edit_days_streak': longest_edit_days_streak,
                   'current_edit_days_streak': current_edit_days_streak,
                   'largest_day_edit_count': largest_day_edit_count,
                   'most_edited_pages': most_edited_pages,
                   'edits_timeline_string': edits_timeline_string,
                   'namespace_piechart_string': namespace_piechart_string,
                   'namespace_unique_piechart_string': namespace_unique_piechart_string,
                   'hour_column_chart_string': hour_column_chart_string,
                   'hour_day_bubble_chart_string': hour_day_bubble_chart_string,
                   'day_column_chart_string': day_column_chart_string
                   }

	return charts_data

def analyze_page(wiki, db, page):
	edits_collection = db['edits']

	user_ids = []
	hour_dict = dict((a, {'count': 0, 'string': '{0}:00'.format("%02d" % (a,))}) for a in range(0, 24))
	edits_dict = dict((a, {'day': {'string': DAY_MAPPING[a], 'count': 0}, 'hours': copy.deepcopy(hour_dict)}) for a in range(0, 7))

	edits = list(edits_collection.find({'page_id': page['_id']}, fields=['user_id', 'timestamp', 'upload', 'new_page']))

	total_edit_count = len(edits)

	# Add hourly edits data to dict
	for edit in edits:
		user_ids.append(edit['user_id'])

		# Add hourly edits data to dict
		edit_hour = edit['timestamp'].hour
		edit_day = edit['timestamp'].weekday()
		edits_dict[edit_day]['hours'][edit_hour]['count'] += 1
		edits_dict[edit_day]['day']['count'] += 1

	creation_edit = edits_collection.find_one({'page_id': page['_id'], 'new_page': True}, fields=['user_id', 'timestamp'])
	creation_date = creation_edit['timestamp'].strftime("%d %B %Y")
	days_since_first_edit = (datetime.datetime.today() - creation_edit['timestamp']).days

	edits_per_day = '%.2f' % (float(total_edit_count)/float(days_since_first_edit))
	days_per_edit = '%.2f' % (float(days_since_first_edit)/float(total_edit_count))

	distinct_editors_count = len(edits_collection.find({'page_id': page['_id']}, fields=[]).distinct('user_id'))

	is_redirect = page['redirect']

	# Format numbers with separators
	locale.setlocale(locale.LC_ALL, 'en_US.utf8')
	total_edit_count = locale.format("%d", total_edit_count, grouping=True)

	# Generate list of most frequent editors
	most_frequent_editors = process_most_frequent_editors(wiki, db, user_ids)

	# Generate data table string for day/hour bubble chart
	hour_day_bubble_chart_string = process_hour_day_bubble_chart(edits_dict)

	# Generate data table string for hour column chart
	hour_column_chart_string = process_hour_column_chart(edits_dict)

	# Generate data table string for day column chart
	day_column_chart_string = process_day_column_chart(edits_dict)

	charts_data = {'total_edit_count': total_edit_count,
                   'most_edited_pages': most_frequent_editors,
                   'distinct_editors_count': distinct_editors_count,
                   'is_redirect': is_redirect,
                   'edits_per_day': edits_per_day,
                   'days_per_edit': days_per_edit,
                   'creation_date': creation_date,
                   'hour_column_chart_string': hour_column_chart_string,
                   'hour_day_bubble_chart_string': hour_day_bubble_chart_string,
                   'day_column_chart_string': day_column_chart_string
                   }

	return charts_data

def analyze_wiki(wiki, db):
	edits_collection = db['edits']
	users_collection = db['users']
	pages_collection = db['pages']

	start_date = get_creation_datetime_from_string(config['wikis'][wiki]['creation_date'])
	end_date = datetime.datetime.today()

	edits_timeline = []
	page_ids = []
	user_edits_count = {}
	largest_day_edit_count = 0
	total_edit_count = 0
	last_30_days_edits = 0
	hour_dict = dict((a, {'count': 0, 'string': '{0}:00'.format("%02d" % (a,))}) for a in range(0, 24))
	edits_dict = dict((a, {'day': {'string': DAY_MAPPING[a], 'count': 0}, 'hours': copy.deepcopy(hour_dict)}) for a in range(0, 7))

	for single_date in daterange(start_date, end_date):
		start = datetime.datetime(single_date.year, single_date.month, single_date.day)
		end = start + datetime.timedelta(days=1)
		edits = list(edits_collection.find({'timestamp': {'$gte': start, '$lt': end}}, fields=['timestamp', 'page_id', 'user_id']))

		day_edit_count = len(edits)
		total_edit_count += day_edit_count

		# Keep track of activity in last 30 days
		if (datetime.datetime.today() - single_date).days < 30:
			last_30_days_edits += day_edit_count

		# Keep track of largest edit counts in a day
		if day_edit_count > largest_day_edit_count:
			largest_day_edit_count = day_edit_count

		for edit in edits:
			page_ids.append(edit['page_id'])

			# Add hourly edits data to dict
			edit_hour = edit['timestamp'].hour
			edit_day = edit['timestamp'].weekday()
			edits_dict[edit_day]['hours'][edit_hour]['count'] += 1
			edits_dict[edit_day]['day']['count'] += 1

			# Increment user edit count
			if edit['user_id'] in user_edits_count:
				user_edits_count[edit['user_id']] += 1
			else:
				user_edits_count[edit['user_id']] = 1

		entry = """[new Date({year}, {month}, {day}), {edits}, {total_edits}]"""

		editentry = entry.format(year=single_date.year,
                                 month=single_date.month-1,
                                 day=single_date.day,
                                 edits=day_edit_count,
                                 total_edits=total_edit_count
                                 )

		edits_timeline.append(editentry)

	user_registrations_timeline = []
	total_user_count = 0

	for week_start_date in weeklydaterange(start_date, end_date):
		start = datetime.datetime(week_start_date.year, week_start_date.month, week_start_date.day)
		end = start + datetime.timedelta(days=7)
		user_registrations = users_collection.find({'registration': {'$gte': start, '$lt': end}}, fields=[]).count()
		total_user_count += user_registrations

		entry = """[new Date({year}, {month}, {day}), {user_registrations}, {total_user_count}]"""

		usersentry = entry.format(year=week_start_date.year,
                                  month=week_start_date.month-1,
                                  day=week_start_date.day,
                                  user_registrations=user_registrations,
                                  total_user_count=total_user_count
                                  )

		user_registrations_timeline.append(usersentry)

	distinct_pages_count = len(edits_collection.find({}, fields=[]).distinct('page_id'))

	days_since_first_edit = (datetime.datetime.today() - start_date).days

	time_period = (end_date - start_date).days + 1
	edits_per_day = '%.2f' % (float(total_edit_count)/float(time_period))
	edits_per_day_30days = '%.2f' % (float(last_30_days_edits)/30.0)

	start_date = start_date.strftime("%d %B %Y")

	# Format numbers with separators
	locale.setlocale(locale.LC_ALL, 'en_US.utf8')
	total_edit_count = locale.format("%d", total_edit_count, grouping=True)
	distinct_pages_count = locale.format("%d", distinct_pages_count, grouping=True)
	days_since_first_edit = locale.format("%d", days_since_first_edit, grouping=True)
	largest_day_edit_count = locale.format("%d", largest_day_edit_count, grouping=True)

	# Generate list of most edited pages
	most_edited_pages = process_most_edited_pages(wiki, db, page_ids)

	# Generate data table string for day/hour bubble chart
	hour_day_bubble_chart_string = process_hour_day_bubble_chart(edits_dict)

	# Generate data table string for hour column chart
	hour_column_chart_string = process_hour_column_chart(edits_dict)

	# Generate data table string for day column chart
	day_column_chart_string = process_day_column_chart(edits_dict)

	# Generate data table string for namespace pie chart
	namespace_piechart_string = process_namespace_pie_chart(wiki, db, edits_collection)

	# Generate data table string for language pie chart
	language_piechart_string = process_language_pie_chart(wiki, db, pages_collection)

	# Generate data table string for language edits distribution pie chart
	language_edits_piechart_string = process_language_edits_pie_chart(wiki, db, pages_collection, edits_collection)

	# Generate data table string for namespace distribution pie chart
	namespace_distribution_piechart_string = process_namespace_distribution_pie_chart(wiki, db, edits_collection)

	# Generate data table string for edits timeline chart
	edits_timeline_string = ',\n'.join(sorted(edits_timeline))

	# Generate data table string for user registrations timeline chart
	user_registrations_timeline_string = ',\n'.join(sorted(user_registrations_timeline))

	# Generate data table string for top editors
	top_editors_string = process_top_editors(wiki, db, user_edits_count)

	charts_data = {'start_date': start_date,
	               'total_edit_count': total_edit_count,
                   'distinct_pages_count': distinct_pages_count,
                   'days_since_first_edit': days_since_first_edit,
                   'edits_per_day': edits_per_day,
                   'edits_per_day_30days': edits_per_day_30days,
                   'largest_day_edit_count': largest_day_edit_count,
                   'most_edited_pages': most_edited_pages,
                   'edits_timeline_string': edits_timeline_string,
                   'user_registrations_timeline_string': user_registrations_timeline_string,
                   'top_editors_string': top_editors_string,
                   'namespace_piechart_string': namespace_piechart_string,
                   'namespace_distribution_piechart_string': namespace_distribution_piechart_string,
                   'language_piechart_string': language_piechart_string,
                   'language_edits_piechart_string': language_edits_piechart_string,
                   'hour_column_chart_string': hour_column_chart_string,
                   'hour_day_bubble_chart_string': hour_day_bubble_chart_string,
                   'day_column_chart_string': day_column_chart_string
                   }

	return charts_data
