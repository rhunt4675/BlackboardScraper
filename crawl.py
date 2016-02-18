from lxml import html
import requests
import json
import smtplib
import getpass
import os
import sys
from email.mime.text import MIMEText

def main():
	try:
		with open(pwd + '/.crawl_profile', 'r+') as profile:
			loginDict = json.load(profile)
		crawl(loginDict)
	except ValueError:
		print "Your .crawl_profiile seems to be corrupted."
		print "Try deleting it and running the program again."
		print
	except IOError:
	        print "Warning: '.crawl_profile' not found."
        	print "This looks like the first time you've run this tool."
	        print "Let's create your persistent profile."
        	print

		login = getUserInfo();
		with open(pwd + '/.crawl_profile', 'w') as profile:
			json.dump(login, profile)

def crawl(loginDict):
	try:
		with open(pwd + '/grades.json') as inFile:
			inData = json.load(inFile)
	except ValueError:
		inData = {}
	except IOError:
		inData = {}
		pass

	r = requests.session()

	r.get("https://blackboard.mines.edu/")
	payload = {'user_id':loginDict['bUser'], 'password':loginDict['bPass'].decode('base64'), 'login':'Login', 'action':'login', 'new_loc':''}
	r.post("https://blackboard.mines.edu/webapps/login/", data=payload)

	classList = getClassList(r)
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

			tempJson = {"date":date, "score":score, "max":max}

			if not myClass in inData:
				inData[myClass] = {}
			if not name in inData[myClass]:
				inData[myClass][name] = tempJson
				alarm(classList[myClass], name, date, score, max, loginDict)
			elif inData[myClass][name] != tempJson:
				inData[myClass][name] = tempJson
				alarm(classList[myClass], name, date, score, max, loginDict)

	with open(pwd + '/grades.json', 'w') as outFile:
		json.dump(inData, outFile)
	outFile.close()

	return

def getClassList(session):
	response = session.post("https://blackboard.mines.edu/webapps/streamViewer/streamViewer?cmd=loadStream&streamName=mygrades")
	parsed_json = json.loads(response.text)
	return parsed_json['sv_extras']['sx_filters'][0]['choices']

def alarm(myClass, assignment, date, score, max, login):
	print "Sending Alarm: {} graded {} on {}. You scored {} out of a possible {}.".format(myClass, assignment, date, score, max)
	msg = MIMEText("{} -- {} on {}. You scored {} out of a possible {}.".format(myClass, assignment, date, score, max))
	msg['To'] = login['To']
	msg['From'] = login['From']

	try:
		smtpclient = smtplib.SMTP(login['Server'], int(login['Port']))
		smtpclient.ehlo()
		smtpclient.starttls()
		smtpclient.ehlo()
		smtpclient.login(login['eUser'], login['ePass'].decode('base64'))
		smtpclient.sendmail([msg['From']], [msg['To']], msg.as_string())
		smtpclient.quit()
	except SMTPException:
		print "SMTP Exception: Either the SMTP server is down or cannot be reached."
		print "Please try again later."
	return

def getUserInfo():
	profile = {}
	profile['bUser'] = raw_input("Blackboard Username: ")

	while True:
		profile['bPass'] = getpass.getpass("Blackboard Password: ").encode('base64')
		if profile['bPass'] == getpass.getpass("Blackboard Password (confirm): ").encode('base64'):
			break
		print
		print "Passwords inconsistent. Please try again."
		print

	profile['To'] = raw_input("Mobile number: ") + '@'
	profile['To'] += raw_input("Notification Destination (vtext.com, att.net, tmomail.net): ")
	profile['From'] = raw_input("Return Address (enter a valid email address): ")

	while True:
		profile['Server'] = raw_input("SMTP Server (smtp.comcast.net, [other?]): ")
		profile['Port'] = raw_input("SMTP Server Port (25, 587): ")
		profile['eUser'] = raw_input("SMTP Server Username: ")
		profile['ePass'] = getpass.getpass("SMTP Server Password: ").encode('base64')
		if testSMTP(profile):
			break;
		print
		print "SMTP server login failed. Please try again."
		print

	#profile['Interval'] = raw_input("Update interval (10-60 min): ")

	print
	print "Profile verified successfully."
	print "Install into crontab with: "
	print
	print "(crontab -l ; echo '0,30 * * * * python {}/crawl.py') | crontab -".format(pwd)
	print

	return profile

def testSMTP(profile):
	try:
		smtpclient = smtplib.SMTP(profile['Server'], int(profile['Port']))
                smtpclient.ehlo()
                smtpclient.starttls()
                smtpclient.login(profile['eUser'], profile['ePass'].decode('base64'))
		smtpclient.quit()
		return True
	except smtplib.SMTPAuthenticationError:
		return False


if __name__ == '__main__':
	global pwd
	pwd = os.path.abspath(__file__).rsplit('/', 1)[0] 
	main()
