from lxml import html
import requests
import json
import smtplib
import getpass
import base64
import os
import sys
import re
from email.mime.text import MIMEText

def main():
	# Open persistent profile configuration file
	try:
		with open(pwd + '/.crawl_profile', 'r+') as profile:
			loginDict = json.load(profile)

		# Check for grades using provided credentials
		crawl(loginDict)
	except ValueError:
		print("Your .crawl_profile seems to be corrupted.", file=sys.stderr)
		print("Try deleting it and running the program again.", file=sys.stderr)
		print(file=sys.stderr)
	except IOError:
		print("Warning: '.crawl_profile' not found.", file=sys.stderr)
		print("This looks like the first time you've run this tool.", file=sys.stderr)
		print("Let's create your persistent profile.", file=sys.stderr)
		print()

		# Create profile if none exists
		login = getUserInfo()
		with open(pwd + '/.crawl_profile', 'w') as profile:
			json.dump(login, profile)

def crawl(loginDict):
	# Load grade information which is not new and has already been sent to the user (from grades.json)
	try:
		with open(pwd + '/grades.json') as inFile:
			inData = json.load(inFile)
	except ValueError:
		inData = {}
	except IOError:
		inData = {}

	# Create an HTTP session
	r = requests.session()

	# Login to Blackboard using loginDict credentials
	r.get("https://blackboard.mines.edu/")
	payload = {'user_id':loginDict['bUser'], 'password':loginDict['bPass'], 'login':'Login', 'action':'login', 'new_loc':''}
	r.post("https://blackboard.mines.edu/webapps/login/", data=payload)

	# Get a list of student's classes
	classList = getClassList(r)

	# For each class, parse an XML tree (using XPATH) to grab the name, date, score, and max score for each assignment
	for myClass in classList:
		grades = r.get("https://blackboard.mines.edu/webapps/bb-mygrades-BBLEARN/myGrades?course_id="+myClass+"&stream_name=mygrades")
		tree = html.fromstring(grades.content)

		rows = tree.xpath('//div[contains(@class, "graded_item_row")]')
		for row in rows:
			name = row.xpath('./div[1]/text()')
			name = (name and name[0].strip()) or (row.xpath('./div[1]/a/text()') and row.xpath('./div[1]/a/text()')[0].strip()) or None
			date = row.xpath('./div[2]/span[1]/text()')
			date = (date and date[0]) or None
			score = row.xpath('./div[3]/span[1]/text()')
			score = (score and score[0]) or None
			max = row.xpath('./div[3]/span[2]/text()')
			max = (max and max[0].strip()[1:]) or None
			strikes = inData[myClass][name]['strikes'] if (inData.get(myClass, {}).get(name, {}).get('strikes')) else 0

			tempJson = {"date":date, "score":score, "max":max, "strikes":strikes}

			# Add a class to grades.json if it hasn't already been added
			if not myClass in inData:
				inData[myClass] = {}

			# Notify student about a new assignment that has been created
			if not name in inData[myClass]:
				inData[myClass][name] = tempJson
				alarm(classList[myClass], name, date, score, max, loginDict)

			# Notify student about an assignment where some aspect has changed (Date, Score, Max Score)
			elif inData[myClass][name] != tempJson:

				# Increment the strikes counter
				inData[myClass][name]['strikes'] += 1
				tempJson['strikes'] += 1

				# If this is the nth consecutive time an aspect has changed, accept it as valid
				if inData[myClass][name]['strikes'] > 20:
					inData[myClass][name] = tempJson
					inData[myClass][name]['strikes'] = 0
					alarm(classList[myClass], name, date, score, max, loginDict)

				# Debug for erroneous notifications
				print("An aspect of an assignment has changed in some way (this may be erroneous).", file=sys.stderr)
				print("Strike counter (consecutive): {}".format(inData[myClass][name]['strikes']), file=sys.stderr)
				print("Here is the old JSON for {} in {}: {}".format(name, classList[myClass], inData[myClass][name]), file=sys.stderr)
				print("Here is the new JSON for {} in {}: {}".format(name, classList[myClass], tempJson), file=sys.stderr)

			# Reset strike counter
			else:
				inData[myClass][name]['strikes'] = 0

	# Write out the updated JSON for persistence
	with open(pwd + '/grades.json', 'w') as outFile:
		json.dump(inData, outFile)

	return

def getClassList(session, iter=0):
	# Attempt to get a list of student's classes
	response = session.post("https://blackboard.mines.edu/webapps/streamViewer/streamViewer?cmd=loadStream&streamName=mygrades")
	parsed_json = json.loads(response.text)
	try:
		classList = parsed_json['sv_extras']['sx_filters'][0]['choices']
	except IndexError:
		if iter > 9:
			print("Getting class list failed.", file=sys.stderr)
			return []

		# Retry post request up to 10 times
		classList = getClassList(session, iter + 1)
	return classList

def alarm(myClass, assignment, date, score, max, login):
	# Generate a customized SMS message and duplicate to STDOUT
	alarmTxt = "{} -- {} on {}. You scored {} out of a possible {}.".format(myClass, assignment, date, score, max)
	print(alarmTxt)

	# Observe 160 char SMS message limit
	msgs = re.findall("..{,155}", alarmTxt)
	mimemsgs = []
	for msg in msgs:
		tempMimeMsg = MIMEText(msg)
		tempMimeMsg['To'] = login['To']
		tempMimeMsg['From'] = login['From']
		mimemsgs.append(tempMimeMsg)

	# Attempt to login to provided SMTP server with provided credentials and send the message
	try:
		smtpclient = smtplib.SMTP(login['Server'], int(login['Port']))
		smtpclient.ehlo()
		smtpclient.starttls()
		smtpclient.ehlo()

		# Iterate through list of 160-char messages
		smtpclient.login(login['eUser'], login['ePass'])
		for msg in mimemsgs:
			smtpclient.sendmail([msg['From']], [msg['To']], msg.as_string())

		# Close SMTP session
		smtpclient.quit()
	except SMTPException:
		print("SMTP Exception: Either the SMTP server is down or cannot be reached.", file=sys.stderr)
		print("Please try again later.", file=sys.stderr)
	return

def getUserInfo():
	# Prompt user for Blackboard & SMTP credentials as well as a notification address, then help them install a crontab job
	profile = {}
	profile['bUser'] = input("Blackboard Username: ")

	while True:
		profile['bPass'] = getpass.getpass("Blackboard Password: ")
		if profile['bPass'] == getpass.getpass("Blackboard Password (confirm): "):
			break
		print()
		print("Passwords inconsistent. Please try again.")
		print()

	profile['To'] = input("Mobile number: ") + '@'
	profile['To'] += input("Notification Destination (vtext.com, txt.att.net, tmomail.net): ")
	profile['From'] = input("Return Address (enter a valid email address): ")

	while True:
		profile['Server'] = input("SMTP Server (smtp.comcast.net, [other?]): ")
		profile['Port'] = input("SMTP Server Port (25, 587): ")
		profile['eUser'] = input("SMTP Server Username: ")
		profile['ePass'] = getpass.getpass("SMTP Server Password: ")
		if testSMTP(profile):
			break;
		print()
		print("SMTP server login failed. Please try again.")
		print()

	print()
	print("Profile verified successfully.")
	print("Install into crontab with: ")
	print()
	print("$ (crontab -l ; echo '0,30 * * * * python {}/crawl.py 1>/dev/null') | sort | uniq | crontab -".format(pwd))
	print()

	return profile

def testSMTP(profile):
	# Verify that the provided SMTP credentials actually "work" before accepting them
	try:
		smtpclient = smtplib.SMTP(profile['Server'], int(profile['Port']))
		smtpclient.ehlo()
		smtpclient.starttls()
		smtpclient.login(profile['eUser'], profile['ePass'])
		smtpclient.quit()
		return True
	except smtplib.SMTPAuthenticationError:
		return False


if __name__ == '__main__':
	global pwd
	pwd = os.path.abspath(__file__).rsplit('/', 1)[0]
	main()
