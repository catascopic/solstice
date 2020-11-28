import asyncio
import websockets
import re
import json

from websockets.exceptions import ConnectionClosedError
from threading import Lock

lock = Lock()
connections = {}

messages = []

name_pattern = re.compile('/([A-Z]{3})')

async def connect(websocket, path):
	match = name_pattern.fullmatch(path)
	if match == None:
		await websocket.close(1002, 'invalid')
		return

	name = match.group(1)

	with lock:
		if name in connections:
			await websocket.close(1002, 'duplicate')
			return
		connections[name] = websocket
		
	print(f'{name} connected, {len(connections)} total')

	try:
		async for message in websocket:
			await broadcast(name, message)
	except ConnectionClosedError:
		# this is raised if the socket closes without an error code
		# in this case, I don't think we should care
		pass

	del connections[name]
	print(f'{name} disconnected, {len(connections)} total')


async def broadcast(source, signal):
	message = json.dumps({'name': source, 'signal': signal})
	for name, websocket in connections.items():
		if name != source:
			await websocket.send(message)

start_server = websockets.serve(connect, port=3637)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
