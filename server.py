import flask
import os
from flask import Flask
from flask import request
from threading import RLock

lock = RLock()

names_in_use = set()

app = Flask(__name__)

@app.route('/')
def home():
	return flask.redirect('/home/', code=302)
	
	
@app.route('/morse/')
def morse():
	names_in_use.add(request.args.get('name'))
	return flask.send_from_directory('morse', 'index.html')
	
	
@app.route('/checkname/<string:name>')
def check_name(name):
	if name in names_in_use:
		return '', 403
	return '', 200


@app.route('/<path:path>')
def files(path):
	# could this be improved? see https://github.com/python/cpython/blob/master/Lib/http/server.py
	filename = os.path.basename(path)
	if '.' in filename:
		return flask.send_from_directory('.', path)
	if not path.endswith('/'):
		return flask.redirect('/' + path + '/', code=301)	
	return flask.send_from_directory('.', os.path.join(path, 'index.html'))


app.run(host='0.0.0.0', port=80, debug=False)
