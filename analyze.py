# -*- coding: utf-8 -*-
import datetime, copy
import pymongo
from config import config

DAY_MAPPING = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
NAMESPACE_MAPPING = {0: 'Main',
                     1: 'Talk',
                     2: 'User',
                     3: 'User talk',
                     4: '{wiki_name} Wiki',
                     5: '{wiki_name} Wiki talk',
                     6: 'File',
                     7: 'File talk',
                     8: 'MediaWiki',
                     9: 'MediaWiki talk',
                    10: 'Template',
                    11: 'Template talk',
                    12: 'Help',
                    13: 'Help talk',
                    14: 'Category',
                    15: 'Category talk'
                     }

def daterange(start_date, end_date):
	for n in range(int((end_date - start_date).days) + 1):
		yield start_date + datetime.timedelta(days=n)

def get_date_range(db, user):
	if db['edits'].find_one({'user_id': user['_id']}, fields=[]) is None:
		return datetime.datetime(2010, 6, 4), datetime.datetime.now()

	user_start = (db['edits'].find({'user_id': user['_id']}, fields=['date'], sort=[('date', pymongo.ASCENDING)]).limit(1))[0]['date']
	user_end = (db['edits'].find({'user_id': user['_id']}, fields=['date'], sort=[('date', pymongo.DESCENDING )]).limit(1))[0]['date']

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

def process_namespace_pie_chart(wiki, edits_collection, user):
	namespace_piechart_output = []
	for namespace in NAMESPACE_MAPPING:
		count = edits_collection.find({'user_id': user['_id'], 'ns': namespace}, fields=[]).count()
		if count > 0:
			namespace_piechart_output.append('[\'{0}\', {1}]'.format(NAMESPACE_MAPPING[namespace].format(wiki_name=config['wikis'][wiki]['wiki_name']), count))
	namespace_piechart_output = ',\n'.join(namespace_piechart_output)

	return namespace_piechart_output

def analyze_user(wiki, db, user):
	edits_collection = db['edits']

	start_date, end_date = get_date_range(db, user)

	edits_timeline = []
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
		date_index_string = '{0}-{1}-{2}'.format(single_date.year, single_date.month, single_date.day)
		edits = edits_collection.find({'user_id': user['_id'], 'date_string': date_index_string}, fields=['date'])

		day_edit_count = edits.count()
		total_edit_count += day_edit_count

		# Keep track of activity in last 30 days
		if ((datetime.datetime.today() - datetime.timedelta(days=1)) - single_date).days < 30:
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

		# Add hourly edits data to dict
		for edit in edits:
			edit_hour = edit['date'].hour
			edit_day = edit['date'].weekday()
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

	# Check if edit streak is running to today and not just to end of last edit
	# Add extra day to allow for user adding edit before the end of the current day	
	if end_date.date() < datetime.datetime.today().date() - datetime.timedelta(days=1):
		current_edit_days_streak = 0

	distinct_pages_count = len(edits_collection.find({'user_id': user['_id']}, fields=[]).distinct('title'))

	days_since_first_edit = (datetime.datetime.today() - start_date).days

	time_period = (end_date - start_date).days
	if time_period == 0:
		edits_per_day = '0.00'
		activity_percentage = '0.00'
		edits_per_day_30days = '0.00'
		activity_percentage_30days = '0.00'
	else:
		edits_per_day = '%.2f' % (float(total_edit_count)/float(time_period))
		activity_percentage = '%.2f' % (100 * float(active_days)/float(time_period))
		edits_per_day_30days = '%.2f' % (float(last_30_days_edits)/30.0)
		activity_percentage_30days = '%.2f' % (100 * float(last_30_days_active_days)/30.0)

	start_date = start_date.strftime("%d %B %Y")
	end_date = end_date.strftime("%d %B %Y")

	# Generate data table string for day/hour bubble chart
	hour_day_bubble_chart_string = process_hour_day_bubble_chart(edits_dict)

	# Generate data table string for hour column chart
	hour_column_chart_string = process_hour_column_chart(edits_dict)

	# Generate data table string for day column chart
	day_column_chart_string = process_day_column_chart(edits_dict)

	# Generate data table string for namespace pie chart
	namespace_piechart_string = process_namespace_pie_chart(wiki, edits_collection, user)

	# Generate data table string for edits timeline chart
	edits_timeline_string = ',\n'.join(sorted(edits_timeline))

	charts_data = {'start_date': start_date,
                   'end_date': end_date,	
	               'total_edit_count': total_edit_count,
                   'distinct_pages_count': distinct_pages_count,
                   'days_since_first_edit': days_since_first_edit,
                   'edits_per_day': edits_per_day,
                   'activity_percentage': activity_percentage,
                   'edits_per_day_30days': edits_per_day_30days,
                   'activity_percentage_30days': activity_percentage_30days,
                   'longest_edit_days_streak': longest_edit_days_streak,
                   'current_edit_days_streak': current_edit_days_streak,
                   'largest_day_edit_count': largest_day_edit_count,
                   'edits_timeline_string': edits_timeline_string,
                   'namespace_piechart_string': namespace_piechart_string,
                   'hour_column_chart_string': hour_column_chart_string,
                   'hour_day_bubble_chart_string': hour_day_bubble_chart_string,
                   'day_column_chart_string': day_column_chart_string
                   }

	return charts_data
