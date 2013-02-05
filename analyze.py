import json, datetime, copy
import pymongo
from config import config

DAY_MAPPING = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}

def daterange(start_date, end_date):
	for n in range(int((end_date - start_date).days) + 1):
		yield start_date + datetime.timedelta(days=n)

def get_date_range(db, user):
	if db['edits'].find({'user_id': user['_id']}).count() == 0:
		return datetime.datetime(2010, 6, 4), datetime.datetime.now()

	user_start = (db['edits'].find({'user_id': user['_id']}, sort=[('date', pymongo.ASCENDING)]).limit(1))[0]['date']
	user_end = (db['edits'].find({'user_id': user['_id']}, sort=[('date', pymongo.DESCENDING )]).limit(1))[0]['date']

	return user_start, user_end

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

def process_namespace_pie_chart(edits_collection, user):
	namespace_piechart_output = []
	for namespace in config['namespaces']:
		count = edits_collection.find({'ns': namespace, 'user_id': user['_id']}).count()
		if count > 0:
			namespace_piechart_output.append('[\'{0}\', {1}]'.format(config['namespaces'][namespace], count))
	namespace_piechart_output = ',\n'.join(namespace_piechart_output)

	return namespace_piechart_output

def analyze_user(db, user, user2=None):
	edits_collection = db['edits']
	patches_collection = db['patches']

	start_date, end_date = get_date_range(db, user)

	edits_timeline = []
	largest_day_edit_count = 0
	longest_edit_days_streak = 0
	current_edit_days_streak = 0
	total_edit_count = 0
	hour_dict = dict((a, {'count': 0, 'string': '{0}:00'.format("%02d" % (a,))}) for a in range(0, 24))
	edits_dict = dict((a, {'day': {'string': DAY_MAPPING[a], 'count': 0}, 'hours': copy.deepcopy(hour_dict)}) for a in range(0, 7))

	for single_date in daterange(start_date, end_date + datetime.timedelta(days=1)):
		date_index_string = '{0}-{1}-{2}'.format(single_date.year, single_date.month, single_date.day)
		edits = list(edits_collection.find({'date_string': date_index_string, 'user_id': user['_id']}))

		day_edit_count = len(edits)
		total_edit_count += day_edit_count

		# Keep track of largest edit counts in a day
		if day_edit_count > largest_day_edit_count:
			largest_day_edit_count = day_edit_count

		# Keep track of edit days streak
		if day_edit_count > 0:
			current_edit_days_streak += 1
			if current_edit_days_streak > longest_edit_days_streak:
				longest_edit_days_streak = current_edit_days_streak
		else:
			current_edit_days_streak = 0

		# Add hourly edits data to dict
		for edit in edits:
			edit_hour = edit['date'].hour
			edit_day = edit['date'].weekday()
			edits_dict[edit_day]['hours'][edit_hour]['count'] += 1
			edits_dict[edit_day]['day']['count'] += 1

		patch = patches_collection.find_one({'date_string': date_index_string})

		if patch:
			entry = """[new Date({year}, {month}, {day}), {edits1}, {total_edits}, \'{title}\', \'{link}\']"""
		else:
			entry = """[new Date({year}, {month}, {day}), {edits1}, {total_edits}, undefined, undefined]"""
		
		if patch:
			editentry = entry.format(year=single_date.year,
									 month=single_date.month-1,
									 day=single_date.day,
									 edits1=day_edit_count,
									 total_edits=total_edit_count,
									 title=patch['patch_name'],
									 link='http://wiki.tf/' + patch['d'].strftime('%d %B, %Y Patch').replace(' ', '_')
									 )
		else:
			editentry = entry.format(year=single_date.year,
									 month=single_date.month-1,
									 day=single_date.day,
									 edits1=day_edit_count,
									 total_edits=total_edit_count
									 )

		edits_timeline.append(editentry)

	distinct_pages_count = len(edits_collection.find({'user_id': user['_id']}).distinct('title'))

	# Generate data table string for day/hour bubble chart
	hour_day_bubble_chart_string = process_hour_day_bubble_chart(edits_dict)

	# Generate data table string for hour column chart
	hour_column_chart_string = process_hour_column_chart(edits_dict)

	# Generate data table string for day column chart
	day_column_chart_string = process_day_column_chart(edits_dict)

	# Generate data table string for namespace pie chart
	namespace_piechart_string = process_namespace_pie_chart(edits_collection, user)

	# Generate data table string for edits timeline chart
	edits_timeline_string = ',\n'.join(sorted(edits_timeline))

	charts_data = {'distinct_pages_count': distinct_pages_count,
				   'longest_edit_days_streak': longest_edit_days_streak,
				   'largest_day_edit_count': largest_day_edit_count,
				   'edits_timeline_string': edits_timeline_string,
				   'namespace_piechart_string': namespace_piechart_string,
				   'hour_column_chart_string': hour_column_chart_string,
				   'hour_day_bubble_chart_string': hour_day_bubble_chart_string,
				   'day_column_chart_string': day_column_chart_string
				   }

	return charts_data

# def analyze_all(db):
# 	edits_collection = db['edits']
# 	entry = '''[new Date({year}, {month}, {day}), {edits1}, {total_edits}, undefined, undefined]'''

# 	start_date = datetime.datetime(2010, 6, 4)
# 	end_date = datetime.datetime.today()

# 	data_list = []
# 	total_edit_count = 0
# 	for single_date in daterange(start_date, end_date):
# 		date_index_string = '%s-%s-%s' % (single_date.year, single_date.month, single_date.day)
# 		edit_count = edits_collection.find({'date_string': date_index_string}).count()
		
# 		total_edit_count += edit_count
# 		editentry = entry.format(year=single_date.year,
# 												month=single_date.month-1,
# 												day=single_date.day,
# 												edits1=edit_count,
# 												total_edits=total_edit_count
# 												)

# 		data_list.append(editentry)

# 	data_list = ',\n'.join(sorted(data_list))

# 	piechart_output = ['[\'Namespace\', \'Edits\']']
# 	for namespace in NAMESPACE_MAP:
# 		count = edits_collection.find({'ns': namespace}).count()
# 		if count > 0:
# 			piechart_output.append('[\'%s\',  %s]' % (NAMESPACE_MAP[namespace], count))
# 	piechart_output = ',\n'.join(piechart_output)

# 	return data_list, piechart_output
