import re
import json
import random
import asyncio
import websockets

from enum import Enum
from threading import Lock
from websockets.exceptions import ConnectionClosedError

connection_lock = Lock()
message_lock = Lock()
goal_lock = Lock()

clients = {}
messages = []

goals_left = 32

NAME_PATTERN = re.compile('/([A-Z]{3})')


class State(Enum):
	CONNECT = 1
	RECONNECT = 2
	DISCONNECT = 3


async def connect(socket, path):
	match = NAME_PATTERN.fullmatch(path)
	if match == None:
		await socket.close(1002, 'invalid')
		return

	name = match.group(1)

	with connection_lock:
		client = clients.get(name)
		if client:
			if not client.socket.closed:
				await socket.close(1002, 'duplicate')
				return
			# should this be a method, or am I thinking in Java?
			client.socket = socket
			on_connect(name, State.RECONNECT)
		else:
			client = Client(socket, name)
			clients[name] = client
			on_connect(name, State.CONNECT)
			
	# TODO: check all clients for missing prompts (there should only ever be one!)
	
	await client.handle()
	on_connect(name, State.DISCONNECT)


def on_connect(name, state):
	print(f'{name}: {state.name}, {len(clients)} total')


def new_chat(name):
	buffer = ChatItem(name)
	with message_lock:
		messages.append(buffer)
	return buffer
			

def get_backlog():
	with message_lock:
		return json.dumps([m.to_json() for m in messages])


def choose_fair(chooser):
	active_clients = [client for client in clients.values()
			if client != chooser and not client.socket.closed]
	total = len(active_clients)
	if not total:
		return None
	best = active_clients[0]
	best_fairness = best.get_fairness()
	best.update(total)
	for client in active_clients[1:]:
		fairness = client.get_fairness()
		if fairness < best_fairness:
			best = client
			best_fairness = fairness
		client.update(total)
	best.chosen += 1
	return best


class Client:
	
	def __init__(self, socket, name):
		self.name = name
		self.socket = socket
		self.codebook = [('hippo', 'christmas')]

		self.prompt = None
		self.response = None
		self.depending_clients = set()
		
		self.chances = 0
		self.chosen = 0
		self.rate = 0


	async def handle(self):
		self.next_prompt()
		# TODO: don't send this if there is no prompt
		await self.socket.send(json.dumps({'prompt': self.prompt}))
		chat = new_chat(self.name)
		try:
			async for message in self.socket:
				obj = json.loads(message)
				response = obj.get('response')
				if response:
					await self.check_response(response)
					return

				if obj.get('delete', False):
					chat.pop()
				elif obj.get('newline', False):
					chat = new_chat(self.name)
				else:
					chat.push(obj['letter'])

				await self.broadcast({
					'name': self.name,
					'message': obj})
		except ConnectionClosedError:
			# this is raised if the socket closes without an error code
			# in this case, I don't think we should care
			pass
		# TODO: update all depending clients
		
	
	async def safe_send(self, message):
		if not self.socket.closed:
			try:
				await self.socket.send(message)
				return True
			except ConnectionClosedError:
				pass
		return False

		
	async def broadcast(self, message):
		with connection_lock:
			for client in clients.values():
				if client != self and not client.socket.closed:
					await client.socket.send(message)


	async def check_response(self, response):
		if response == self.response:
			self.next_prompt()
			with goal_lock:
				goals_left -= 1
				goals_temp = goals_left
			await socket.send(json.dumps({
				'prompt': self.prompt, 
				'correct': True, 
				'goals': goals}))
			await self.broadcast({'goals': goals_temp})
		else:
			await socket.send(json.dumps({'correct': False}))
				

	def next_prompt(self):
		with connection_lock:
			contact = choose_fair(self)
		if contact == None:
			return
		# should this part be synchronized?
		contact.depending_clients.add(self)
		self.prompt, self.response = contact.codebook.pop()
			
			
	def update(self, choices):
		# updates the rolling average
		self.rate = (self.chances * self.rate + 1 / choices) / (self.chances + 1)
		self.chances += 1
	

	def get_fairness(self):
		if self.chances == 0:
			return -1
		expected = self.rate * self.chances;
		return (self.chosen - expected) / expected;
		
			
	def __repr__(self):
		return f'{self.name}: {"off" if self.socket.closed else "on"}line'


class ChatItem:

	def __init__(self, name):
		self.name = name
		self.buffer = []
	
	
	def push(self, letter):
		self.buffer.append(letter)
	
	
	def pop(self):
		self.buffer.pop()
		

	def to_json(self):
		return {'name': self.name, 'text': ''.join(self.buffer)}
		
	
	def __repr__(self):
		return f'{self.name}: {"".join(self.buffer)}'


start_server = websockets.serve(connect, port=3637)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
