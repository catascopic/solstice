from string import ascii_uppercase
import itertools

with open("signs.txt", "w") as f:
	for seq in itertools.product(ascii_uppercase, repeat=3):
		f.write(''.join(seq) + '\n')
