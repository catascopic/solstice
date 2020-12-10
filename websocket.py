import re
import json
import random
import asyncio
import websockets

from enum import Enum
from threading import RLock
from websockets.exceptions import ConnectionClosedError

connection_lock = RLock()
message_lock = RLock()
goal_lock = RLock()

clients = {}
messages = []

goals_left = 32

NAME_PATTERN = re.compile('/([A-Z]{3})')


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
			print(f'{name} reconnected')
		else:
			client = Client(socket, name)
			clients[name] = client
			print(f'{name} connected, {len(clients)} total')
			
		check_unpaired()

	await client.handle()
	print(f'{name} disconnected')


def new_chat(name):
	chat = ChatItem(name)
	with message_lock:
		messages.append(chat)
	return chat


def check_unpaired():
	for client in clients.values():
		if not client.prompt:
			await client.send_next_prompt()


def get_backlog():
	with message_lock:
		# do something
		pass


def choose_fair(chooser):
	active_clients = [client for client in clients.values()
		if client != chooser and not client.socket.closed]
	total = len(active_clients)
	if total == 0:
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
		self.chat = new_chat(self.name)
		with open(f'codebooks/{len(clients)}.json') as file:
			self.codebook = json.load(file)
		self.prompts_left = self.codebook.copy()
		random.shuffle(self.prompts_left)

		self.depending_clients = set()
		
		self.chances = 0
		self.chosen = 0
		self.rate = 0
		
		self.next_prompt()
		

	def switch_socket(self, socket):
		self.socket = socket


	async def handle(self):
		# self.socket = socket
		# TODO: don't send this if there is no prompt
		# TODO: send current chat
		await self.safe_send({
			'codebook': self.codebook,
			'goal': goals_left,
			'prompt': self.prompt
		})

		try:
			async for message in self.socket:
				obj = json.loads(message)
				response = obj.get('response')
				if response:
					await self.check_response(response)
					continue

				# TODO: naming!
				content = obj.get('chat')
				if content:
					if obj.get('newline'):
						self.chat = new_chat(self.name)
					self.chat.content = content
					await self.broadcast({'chat': {
						'name': self.name,
						'content': content}})
		except ConnectionClosedError:
			# this is raised if the socket closes without an error code
			# in this case, I don't think we should care
			pass
		# TODO: update all depending clients
		
	
	async def safe_send(self, message):
		if not self.socket.closed:
			try:
				await self.socket.send(json.dumps(message))
				return True
			except ConnectionClosedError:
				pass
		return False


	async def broadcast(self, message):
		with connection_lock:
			for client in clients.values():
				if client != self:
					await client.safe_send(message)


	async def check_response(self, response):
		global goals_left
		if response == self.response:
			self.contact.depending_clients.remove(self)
			self.next_prompt()
			with goal_lock:
				goals_left -= 1
				goals_temp = goals_left
			await self.safe_send({
				'prompt': self.prompt, 
				'feedback': True, 
				'goal': goals_temp})
			await self.broadcast({'goal': goals_temp})
		else:
			await self.safe_send({'feedback': False})
		

	def next_prompt(self):
		with connection_lock:
			self.contact = choose_fair(self)
		if self.contact == None:
			self.prompt = None
			self.response = None
		else:
			# should this part be synchronized?
			self.contact.depending_clients.add(self)
			self.prompt, self.response = self.contact.prompts_left.pop()
			
	
	async def send_next_prompt(self):
		self.next_prompt()
		if self.prompt:
			await self.safe_send({'prompt': self.prompt})
			
			
	def update(self, choices):
		# updates the rolling average
		self.rate = (self.chances * self.rate + 1 / choices) / (self.chances + 1)
		self.chances += 1


	def get_fairness(self):
		if self.chances == 0:
			return -1
		expected = self.rate * self.chances
		return (self.chosen - expected) / expected
		
			
	def __repr__(self):
		return f'{self.name}: {"off" if self.socket.closed else "on"}line {self.socket}'


class ChatItem:

	def __init__(self, name):
		self.name = name
		self.content = ''
		

	def to_json(self):
		return {'name': self.name, 'text': ''.join(self.content)}
		
	
	def __repr__(self):
		return f'{self.name}: {"".join(self.content)}'


start_server = websockets.serve(connect, port=3637)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
