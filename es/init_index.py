from config import script_dir
import subprocess
from time import time
# run rebuild.py

start, end = time(), 0
subprocess.run(['python3', script_dir / 'rebuild.py'], check=True)
end = time()
print(f'Rebuild took {end - start:.2f} seconds')

start = time()
subprocess.run(['python3', script_dir / 'index.py'], check=True)
end = time()
print(f'Indexing took {end - start:.2f} seconds')

start = time()
subprocess.run(['python3', script_dir / 'pg_rank.py'], check=True)
end = time()
print(f'PageRank took {end - start:.2f} seconds')

start = time()
subprocess.run(['python3', script_dir / 'wordvec.py'], check=True)
end = time()
print(f'Word2Vec took {end - start:.2f} seconds')

print('Done')