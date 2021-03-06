import flask
import os
from flask import Flask
from flask import request

names_in_use = set()

app = Flask(__name__)

@app.route('/')
def home():
	return flask.redirect('/home/', code=302)


@app.route('/morse/')
def morse():
	name = request.args.get('name')
	if name:
		names_in_use.add(name)
	return flask.send_from_directory('morse', 'index.html')


@app.route('/checkname/')
def check_name():
	name = request.args.get('name')
	if not name:
		return '', 400
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
