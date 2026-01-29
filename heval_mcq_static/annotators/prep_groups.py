import random, os
random.seed(493)

RESERVED = ['aa-zixian', 'da-best', 'aa-medium']
OPEN = ['aa-50', 'aa-60', 'aa-65', 'matt-top-1k', 'nodding-james', 'video-caption-batch1-ranked', 'video-molmo-caption', 'webolmo-1', 'good-video-olmo']
EXCLUDE = ['blacklist']


def extract_from_file(filepath: str) -> list[str]:    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    if len(lines) > 1:
        # treat as 1 annotator per line
        return [l.strip() for l in lines if l]
    else:
        # treat as comma seperated list
        return [u.strip() for u in lines[0].split(',') if u]

# to determine size of groups
if True:
    r = set()
    for filename in RESERVED:
        r.update(extract_from_file(filename))
    o = set()
    for filename in OPEN:
        o.update(extract_from_file(filename))
    e = set()
    for filename in EXCLUDE:
        e.update(extract_from_file(filename))
        
    print(len(r), len(o), len(e))

total = set()
total.update(extract_from_file('matt-top-1k')[:499])
total.update(extract_from_file('video-caption-batch1-ranked')[:299])
total.update(extract_from_file('good-video-olmo'))
total.difference_update(extract_from_file('blacklist'))
total.difference_update(r)
shuffled = random.sample(list(total), k=len(total))
print(len(shuffled))
n = len(shuffled)
k = n // 3
one, two, three, four = shuffled[:k//2], shuffled[k//2:k], shuffled[k:2*k], shuffled[2*k:]
print(len(one), len(two), len(three), len(four))

os.makedirs('groups', exist_ok=True)
with open('groups/one', 'w') as f:
    for a in one:
        f.write(a + '\n')
with open('groups/two', 'w') as f:
    for a in two:
        f.write(a + '\n')
with open('groups/three', 'w') as f:
    for a in three:
        f.write(a + '\n')
with open('groups/four', 'w') as f:
    for a in four:
        f.write(a + '\n')