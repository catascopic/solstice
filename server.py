import flask
import os
from flask import Flask
from flask import request
from threading import Lock

lock = Lock()
names = set()

app = Flask(__name__)

@app.route('/')
def home():
	return flask.redirect('/morse/', code=302)


@app.route('/<path:path>')
def files(path):
	# could this be improved? see https://github.com/python/cpython/blob/master/Lib/http/server.py
	filename = os.path.basename(path)
	if '.' in filename:
		return flask.send_from_directory('.', path)
	if not path.endswith('/'):
		return flask.redirect(path + '/', code=301)	
	return flask.send_from_directory('.', os.path.join(path, 'index.html'))


@app.route('/transmit/', methods=['POST'])	
def transmit():
	print('signal: ' + request.data.decode('utf-8'))
	return '', 204


app.run(host='0.0.0.0', port=80, debug=False)