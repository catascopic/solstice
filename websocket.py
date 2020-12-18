import re
import json
import random
import asyncio
import websockets

from websockets.exceptions import ConnectionClosedError

clients = {}
messages = []
goals_left = 20

NAME_PATTERN = re.compile('/([A-Z]{3})')


async def connect(socket, path):
	match = NAME_PATTERN.fullmatch(path)
	if not match:
		await socket.close(4000, 'invalid')
		return

	name = match.group(1)

	client = clients.get(name)
	if client:
		if client.online():
			await socket.close(4001, 'duplicate')
			return
		client.socket = socket
		print(f'{name} reconnected')
	else:
		client = Client(socket, name)
		clients[name] = client
		print(f'{name} connected, {len(clients)} total')

	await check_unpaired()
	await client.handle_connection()
	print(f'{name} disconnected')


def online_clients():
	return (client for client in clients.values() if client.online())


def new_chat(name):
	chat = ChatItem(name)
	messages.append(chat)
	return chat


async def check_unpaired():
	for client in online_clients():
		if not client.prompt:
			await client.send_next_prompt()


def chat_history():
	return [chat.__dict__ for chat in messages if chat.content]


async def victory():
	info = video_call_info()
	for client in clients.values():
		await client.safe_send({'victory': info})


def video_call_info():
	with open(f'video-call.json') as file:
		return json.load(file)


def choose_fair(chooser):
	active_clients = [client for client in online_clients() if client != chooser]
	total = len(active_clients)
	if not total:
		return None
	# should we update if there's only 1 choice?
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


def print_pairings():
	for client in clients.values():
		print(f'{client} has a prompt for {client.contact}')


class Client:

	def __init__(self, socket, name):
		self.name = name
		self.socket = socket
		self.active_chat = None
		with open(f'codebooks/{len(clients)}.json') as file:
			self.codebook = json.load(file)
		self.prompts_left = self.codebook.copy()
		random.shuffle(self.prompts_left)

		self.contact = None
		self.cleanup_task = None

		self.chances = 0
		self.chosen = 0
		self.rate = 0

		self.next_prompt()


	async def handle_connection(self):
		if self.cleanup_task:
			self.cleanup_task.cancel()

		await self.send_state()

		try:
			async for message in self.socket:
				await self.handle_message(json.loads(message))
		except ConnectionClosedError:
			# this is raised if the socket closes without an error code
			# in this case, I don't think we should care
			pass
		self.cleanup_task = asyncio.get_event_loop().create_task(self.cleanup())


	async def handle_message(self, message):
		response = message.get('response')
		if response:
			await self.check_response(response)
			return

		chat = message.get('chat')
		if chat:
			to_broadcast = {'name': self.name, 'content': chat}
			if message.get('newline') or not self.active_chat:
				self.active_chat = new_chat(self.name)
				to_broadcast['newline'] = True
			self.active_chat.content = chat
			await self.broadcast({'chat': to_broadcast})


	async def send_state(self):
		state = {'codebook': self.codebook, 'backlog': chat_history()}
		if goals_left > 0:
			state['goal'] = goals_left
		else:
			state['victory'] = video_call_info()
		if self.prompt:
			state['prompt'] = self.prompt
		if self.active_chat:
			state['myChat'] = self.active_chat.content
		await self.safe_send(state)


	def online(self):
		return not self.socket.closed


	async def safe_send(self, message):
		# TODO: is this all necessary?
		if self.online():
			try:
				await self.socket.send(json.dumps(message))
				return True
			except ConnectionClosedError:
				pass
		return False


	async def broadcast(self, message):
		for client in clients.values():
			if client != self:
				await client.safe_send(message)


	async def check_response(self, given_response):
		global goals_left
		if given_response == self.response:
			await self.contact.safe_send({'teamwork': self.name})
			self.next_prompt()
			goals_left -= 1

			if goals_left <= 0:
				await victory()
			else:
				await self.safe_send({
					'prompt': self.prompt, 
					'feedback': True, 
					'goal': goals_left})
				# ideally combine this with the "teamwork" message, but whatever
				await self.broadcast({'goal': goals_left})
		else:
			response = {'feedback': False}
			for client in clients.values():
				if client.contact == self and given_response == client.response:
					response['contactHelp'] = client.name
					break;

			await self.safe_send(response)


	def next_prompt(self):
		self.contact = choose_fair(self)
		if not self.contact:
			self.prompt = None
			self.response = None
		else:
			self.prompt, self.response = self.contact.prompts_left.pop()


	async def send_next_prompt(self):
		self.next_prompt()
		# send null prompt if no users are online?
		if self.prompt:
			await self.safe_send({'prompt': self.prompt})


	async def cleanup(self):
		# user has 30 seconds to reconnect
		await asyncio.sleep(30)
		for client in clients.values():
			if client.contact == self:
				await client.send_next_prompt()


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
		return f'{self.name}, {"on" if self.online() else "off"}line'


class ChatItem:

	def __init__(self, name):
		self.name = name
		self.content = ''


	def __repr__(self):
		return f'{self.name}: {self.content}'


asyncio.get_event_loop().run_until_complete(websockets.serve(connect, port=3637))
asyncio.get_event_loop().run_forever()
