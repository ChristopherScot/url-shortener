
# URL Shortener

This was written primarily as an introduction to using [Zappa](https://github.com/zappa/Zappa) which I only recently found out about. The goal was to use a bunch of amazon services while remaining firmly in the "free tier" category. It also served as a refresher on Flask/Jinja. I'm a backend guy that hates HTML so it ain't pretty, but it does the job. 


## Zappa
- Make sure you have an AWS Profile setup and have run `aws configure`
- Run `zappa init`
- If you want to setup an https site follow [these](https://github.com/zappa/Zappa#deploying-to-a-domain-with-aws-certificate-manager) directions
- Run zappa deploy <env> when you are ready to deploy this to your domain. 
- Run zappa update <env> after making a code change. 

## DynamoDB
#####Two tables were created here: 

<b> users </b>
- username (primary key)
- password (stores a password hash that can be generated by createPasswordHash.py)
- service

<b> url-shortener </b>
- short_url (primary key)
- long_url
- description
- hits

## S3
#### Used to store template files
Just copy templates/index.html and templates/login.html to your S3 Bucket and pass in the bucket name as an env var. 
   ##### Note: S3 bucket names must be globally unique.

## CloudFront 
Cloudfront was used to route traffic to the lambda from a purchased domain. I followed the tutorial [here](https://romandc.com/zappa-django-guide/walk_domain/) and went with [option 3](https://romandc.com/zappa-django-guide/walk_domain/#other-service-providers) the simplest possible method would be [option 1](https://romandc.com/zappa-django-guide/walk_domain/#option-1-route53-and-acm) but I already purchased a domain outside of AWS.
	 
## Environment Variables

Environment variables are configured using zappa_settings.json which is created when you run `zappa init` 

#### Necessary environment variables are:
	
		"AWS_REGION": "us-east-1"
		"USERS_TABLE": "users"
		"TEMPLATE_BUCKET": "some-really-unique-s3-bucket-name-I-usually-preface-them-with-my-name",
		"SECRET_KEY": "your-super-secret-key-that-is-used-to-encode-session-data"

If testing locally you will need to pass in a few other variables as well as the above env vars:

	AWS_ACCESS_KEY_ID=<your aws access key> AWS_SECRET_ACCESS_KEY=<your aws secret key> LOCAL=true 
	

For me this looks like:

	`AWS_ACCESS_KEY_ID=<your aws access key> AWS_SECRET_ACCESS_KEY=<your aws secret key> LOCAL=true AWS_REGION=<the region you've deployed stuff to> TEMPLATE_BUCKET=<bucket name> SECRET_KEY=<something secret and longish> python app.py`

where <These> are obviously replaced by the env value you want to set it to.

## Pulumi

   I've used Pulumi to create the S3 Buckets, DynamodDB Tables etc. that Zappa doesn't create for 
	me. If you wish to use it follow [this tutorial.](https://www.pulumi.com/docs/clouds/aws/get-started/) 

#### The code that I used for this is here:
	<details>
	```python
		"""An AWS Python Pulumi program"""

		import pulumi
		import os
		import pulumi_aws as aws
		from werkzeug.security import generate_password_hash

		bucket_name = os.getenv('TEMPLATE_BUCKET') or 'templates'
		links_table_name = os.getenv('LINKS_TABLE') or 'links'
		users_table_name = os.getenv('USERS_TABLE') or 'users'
		username = os.getenv('USERNAME') or 'test'
		password = os.getenv('PASSWORD') or 'password'

		mainPage = pulumi.asset.FileAsset('../templates/index.html')
		loginPage = pulumi.asset.FileAsset('../templates/login.html')


		# Create an AWS resource (S3 Bucket)
		bucket = aws.s3.Bucket(bucket_name, bucket=bucket_name)
		mainPage_s3 = aws.s3.BucketObject("index.html",
			bucket=bucket.id,
			source=mainPage)

		loginPage_s3 = aws.s3.BucketObject("login.html",
			bucket=bucket.id,
			source=loginPage)

		# Export the name of the bucket
		pulumi.export('bucket_name', bucket.bucket)


		url_shortener_table = aws.dynamodb.Table(links_table_name,
			name=links_table_name,
			attributes=[
				aws.dynamodb.TableAttributeArgs(
					name="short_url",
					type="S",
				),		   
			],
			billing_mode="PROVISIONED",
			hash_key="short_url",
			read_capacity=1,
			write_capacity=1)

		link = aws.dynamodb.TableItem(
			"example-link", 
			table_name=url_shortener_table.name, 
			hash_key=url_shortener_table.hash_key, 
			item="""{
				"short_url": {"S": "g"},
				"long_url": {"S": "google.com"},
				"hits": {"N": "10"},
				"description": {"S": "It is google..."}
				}"""
			)

		users_table = aws.dynamodb.Table(users_table_name,
			name=users_table_name,
			attributes=[
				aws.dynamodb.TableAttributeArgs(
					name="username",
					type="S",
				),		   
			],
			billing_mode="PROVISIONED",
			hash_key="username",
			read_capacity=1,
			write_capacity=1)

		password = generate_password_hash(password)
		item = f'{{"username": {{"S": "{username}"}}, "password": {{"S": "{password}"}}, "service": {{"S": "url-shortener"}}}}'

		user = aws.dynamodb.TableItem(
			"example-user", 
			table_name=users_table.name, 
			hash_key=users_table.hash_key, 
			item=item
			)

		pulumi.export(users_table_name, users_table.name)
		```
	</details>
	
##### Note: You don't NEED to use Pulumi at all and all of this can just be created in the AWS console/web ui.
