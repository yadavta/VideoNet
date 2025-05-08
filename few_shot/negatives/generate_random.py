import random, sys
random.seed(493)

try:
	domain = sys.argv[1].upper()
	if not domain: raise Exception()
except:
	print("pass domain name as first argument to CLI")
	exit(1)

try:
	with open("actions.temp", "r") as f:
   		items = [line.strip() for line in f if line.strip()]
except:
	print("unable to read from actions.temp ... maybe this file doesn't exist ?")
	exit(1)

lines = []
for item in items:
    others = [x for x in items if x != item]
    sampled = random.sample(others, 3)
    lines.append(','.join([item] + sampled))

with open("currently_generating.txt", "a") as out:
	out.write(f"## {domain} ##\n")
	for line in lines:
		out.write(line + '\n')
