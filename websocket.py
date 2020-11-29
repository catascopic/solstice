import asyncio
import websockets
import re
import json

from websockets.exceptions import ConnectionClosedError
from threading import Lock

lock = Lock()
connections = {}
messages = []

NAME_PATTERN = re.compile('/([A-Z]{3})')

async def connect(socket, path):
	match = NAME_PATTERN.fullmatch(path)
	if match == None:
		await socket.close(1002, 'invalid')
		return

	name = match.group(1)

	with lock:
		if name in connections:
			await socket.close(1002, 'duplicate')
			return
		connections[name] = socket
		
	print(f'{name} connected, {len(connections)} total')
	await handle(socket, name)
	del connections[name]
	print(f'{name} disconnected, {len(connections)} total')


async def handle(socket, name):
	buffer = MessageBuffer(name)
	messages.append(buffer)
	try:
		async for message in socket:
			if message == 'delete':
				buffer.delete()
			elif message == 'newline':
				buffer = MessageBuffer(name)
				messages.append(buffer)
			else:
				buffer.add(message)
				
			print(messages)
			await broadcast(name, message)
	except ConnectionClosedError:
		# this is raised if the socket closes without an error code
		# in this case, I don't think we should care
		pass


async def broadcast(name, signal):
	message = json.dumps({'name': name, 'signal': signal})
	for name, socket in connections.items():
		if name != name:
			await socket.send(message)
			

class MessageBuffer:

	def __init__(self, name):
		self.name = name;
		self.buffer = []
	
	
	def add(self, letter):
		self.buffer.append(letter)
	
	
	def delete(self):
		self.buffer.pop()
		

	def toJson(self):
		json.dumps({'name': self.name, 'text': ''.join(self.buffer)})
		
	
	def __repr__(self):
		return f'{self.name}: {"".join(self.buffer)}'


start_server = websockets.serve(connect, port=3637)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
