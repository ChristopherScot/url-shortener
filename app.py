
from flask import Flask, jsonify, redirect, render_template_string, render_template, request, session
from flask_bootstrap import Bootstrap
from zappa.asynchronous import task
import json
from requests import post
from os import getenv
from werkzeug.security import check_password_hash
import boto3


AWS_REGION = getenv("AWS_REGION") 
USERS_TABLE = getenv("USERS_TABLE")
TEMPLATE_BUCKET = getenv("TEMPLATE_BUCKET")
APP_TABLE = getenv("APP_TABLE") or "url-shortener"


app = Flask(__name__)
Bootstrap(app)

# Note: If a SECRET_KEY is not set this super unsafe one will be used. Don't let that happen.
app.config['SECRET_KEY']=getenv("SECRET_KEY") or "SOME SECRET KEY"



def verify_password(username, password):
	print("user:", username," pass:", password)
	if not (username and password):
		print("Username or password not provided")
		return False
	ddb = boto3.resource('dynamodb', region_name = AWS_REGION).Table(USERS_TABLE)
	item = ddb.get_item(Key={'username': username}) 
	if 'Item' not in item:
		print("User not found")
		return False
	user = item['Item']
	
	if check_password_hash(user.get('password'), password) and user.get('service') == 'url-shortener':
		return username
	

def authorized():
	if session.get('user'):
		print("authorized")
		print(session.get('user'))
		return True
	else:
		return False

@app.route('/auth', methods=['POST'])
def auth():
	username = request.form.get('username')
	password = request.form.get('password')
	if verify_password(username, password):
		session['user']=username
		return redirect("/go", code=302)
	else:
		return redirect("/login?status=failed", code=302)
	
@app.route('/health')
def health():
	resp = jsonify(health="healthy")
	resp.status_code = 200
	return resp  
  

ddb = boto3.resource('dynamodb', region_name = AWS_REGION).Table(APP_TABLE)

# Totally not needed... but I hate dealing with dicts when I can use a real object. 
class DictObj:
	def __init__(self, in_dict:dict):
		assert isinstance(in_dict, dict)
		for key, val in in_dict.items():
			if isinstance(val, (list, tuple)):
				setattr(self, key, [DictObj(x) if isinstance(x, dict) else x for x in val])
			else:
				setattr(self, key, DictObj(val) if isinstance(val, dict) else val)

@app.route('/go/delete/<short_url>', methods=['GET'])
def deleteShortURLHandler(short_url):
	if not authorized():
		return redirect("/go/	login", code=302)
	deleteShortURL(short_url)
	return redirect("/go", code=302)

@app.route('/go/delete/<short_url>', methods=['POST'])
def deleteShortURL(short_url):
	if not authorized():
		return redirect("/go/login", code=403)
	try:
		ddb.delete_item(
			Key={
				'short_url': short_url
			}
		)
	except Exception as e:
		resp = jsonify({"error":str(e)})
		resp.status_code = 400
		return(resp)
	return(jsonify({"success":short_url+" deleted"}))

@task
@app.route('/go/login')
def loginPage():
	return render_template("login.html", status=request.args.get('status'))

@app.route('/go', methods=['GET'])
def ShortUrlPage():
	try:
		s3 = boto3.client('s3')
		page="index.html"
		response = s3.get_object(Bucket=TEMPLATE_BUCKET, Key=page)
		data = response['Body'].read().decode('utf-8')
		
	except s3.exceptions.NoSuchBucket as e:
		# S3 Bucket does not exist
		print('The S3 bucket does not exist.')
		print(e)

	except s3.exceptions.NoSuchKey as e:
		# Object does not exist in the S3 Bucket
		print('The S3 objects does not exist in the S3 bucket.')
		print(e)
	try:
		links = [DictObj(link) for link in ddb.scan()['Items']]
	except Exception as e:
		print(e)
		links = []
	
	if getenv("LOCAL"): return render_template("index.html", links=links)
	
	return render_template_string(data, links=links)

@app.route('/go/<short_url>', methods=['GET'])
def shortUrlHandler(short_url):
	return urlShortenerHandler(short_url)


@app.route('/go/update', methods=['POST'])
def shortUrlUpdate():
	if not authorized():
		return redirect("/go/login", code=302)
	if not request.form or not	'long_url' or not 'short_url' in request.form:
			resp = jsonify({"error":"invalid request"})
			resp.status_code = 400
			return(resp)
	short_url = request.form.get('short_url')
	long_url = request.form.get('long_url')
	description = request.form.get('description')
	try:
		response = ddb.get_item(Key={'short_url': short_url})
		item = response['Item']
		item['short_url'] = short_url
		item['long_url'] = long_url
		item['description'] = description
		ddb.put_item(Item=item)
	except Exception as e:
			resp = jsonify({"error":str(e)})
			resp.status_code = 400
			return(resp)

	return redirect("/go", code=302)



@app.route('/go/create/form', methods=['POST'])
def shortUrlCreatorHandler():
	if not authorized():
		return redirect("/go/login", code=302)
	if not request.form or not 'create_long_url' in request.form or not 'create_short_url' in request.form:
			resp = jsonify({"error":"invalid request"})
			resp.status_code = 400	
			return(resp)
	link = {
		'short_url':request.form.get('create_short_url'),
		'long_url':request.form.get('create_long_url'),
		'description':request.form.get('create_description')
	}
	url = f"{request.url_root}/go/create"
	headers = {'Content-Type':'application/json' }
	cookies = {'session':request.cookies.get('session')}
	r = post(url, data=json.dumps(link), headers=headers, cookies=cookies)
	return redirect("/go", code=302)


@app.route('/go/create', methods=['POST'])
def shortUrlCreator():
	if not authorized():
		return redirect("/go/login", code=302)
	if not request.json:
		resp = jsonify({"error":"invalid request"})
		resp.status_code = 400
		return(resp)
	short_url = request.json.get('short_url')
	long_url = request.json.get('long_url')
	description = request.json.get('description')
	try:
		ddb.put_item(
			Item={
				'short_url':short_url,
				'long_url':long_url,
				'description':description,
				'hits':0
			},
			ConditionExpression='attribute_not_exists(short_url)'
		)
	except Exception as e:
			resp = jsonify({"error":str(e)})
			resp.status_code = 400
			return(resp)

	return (f"{short_url} == {long_url}")
	


	
# @task I don't want to do this as a separate task because it will return an async handler, which then can't be returned
# as a json object to the client. 
def urlShortenerHandler(short_url):
	try:
		item = ddb.get_item(Key={'short_url': short_url}) #look up the take the short id value in dynamodb
		# If the shortcut doesn't already exist let's create it.
		if 'Item' not in item:
			return ShortUrlPage(short_url)
			
		long_url = item.get('Item').get('long_url') #take the long_url value corresponding to the short id
		# increase the hit number on the db entry of the url (analytics?)
		ddb.update_item(
			Key={'short_url': short_url},
			UpdateExpression='set hits = hits + :val',
			ExpressionAttributeValues={':val': 1}
		)
	except Exception as e:
		return(str(e))
	if not long_url.startswith("http"):
		return redirect("https://"+long_url, code=302)
	else:
		return redirect(long_url, code=302)
  
if __name__=='__main__':
	app.run(debug=True)

