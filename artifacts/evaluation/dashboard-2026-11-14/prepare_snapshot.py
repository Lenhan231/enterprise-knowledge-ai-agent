"""Export one read-only repeatable-read snapshot and restore an isolated PG17 clone."""
import asyncio, hashlib, json, os, secrets, subprocess
from pathlib import Path
import asyncpg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = OUT / 'dataset'
NAME = 'dashboard-bench-20261114'
def quote(s): return '"' + s.replace('"', '""') + '"'
def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

async def main():
 DATA.mkdir(exist_ok=True)
 if not (DATA/'manifest.json').exists():
  source = await asyncpg.connect(dotenv_values(ROOT/'.env')['ANALYTICS_DATABASE_URL'])
  async with source.transaction(isolation='repeatable_read', readonly=True):
   version = await source.fetchval('SELECT version()')
   tables = await source.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='commerce' AND table_type='BASE TABLE' ORDER BY 1")
   schema = []
   for table, in tables:
    columns = [dict(r) for r in await source.fetch("SELECT a.attname AS name, format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull AS not_null FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='commerce' AND c.relname=$1 AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum", table)]
    constraints = [dict(r) for r in await source.fetch("SELECT con.conname AS name, pg_get_constraintdef(con.oid) AS definition, ARRAY(SELECT a.attname FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum=ANY(con.conkey)) AS columns FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='commerce' AND c.relname=$1 AND con.contype IN ('p','f','u')", table)]
    readable = {r[0] for r in await source.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema='commerce' AND table_name=$1",table)}
    columns = [c for c in columns if c['name'] in readable]
    full_select = await source.fetchval("SELECT has_table_privilege(current_user,$1,'SELECT')",'commerce.'+table)
    file = DATA/(table+'.copy')
    select = 'SELECT '+','.join(quote(c['name']) for c in columns)+' FROM commerce.'+quote(table)
    await source.copy_from_query(select, output=str(file), format='binary')
    count = len(await source.fetch(select))
    schema.append(dict(table=table, columns=columns, constraints=constraints, rows=count, full_select=full_select, sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    print(table, count, flush=True)
   save(DATA/'manifest.json', dict(source_version=version, isolation='repeatable_read readonly', tables=schema, image='postgres:17.6', snapshot_time=await source.fetchval('SELECT transaction_timestamp()')))
  await source.close()
 manifest = json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 for t in manifest['tables']: assert hashlib.sha256((DATA/(t['table']+'.copy')).read_bytes()).hexdigest()==t['sha256']
 password = secrets.token_hex(24)
 env = os.environ.copy(); env['POSTGRES_PASSWORD']=password
 subprocess.run(['docker','run','--detach','--name',NAME,'--publish','127.0.0.1:55432:5432','--env','POSTGRES_PASSWORD','postgres:17.6'],env=env,check=True,stdout=subprocess.DEVNULL)
 for attempt in range(60):
  try:
   conn=await asyncpg.connect(host='127.0.0.1',port=55432,user='postgres',password=password,database='postgres'); break
  except (OSError,asyncpg.PostgresError): await asyncio.sleep(1)
 else: raise RuntimeError('Local PostgreSQL did not start')
 await conn.execute('CREATE SCHEMA commerce; REVOKE CREATE ON SCHEMA public FROM PUBLIC')
 for t in manifest['tables']:
  cols=', '.join(quote(c['name'])+' '+c['type']+(' NOT NULL' if c['not_null'] else '') for c in t['columns'])
  await conn.execute('CREATE TABLE commerce.'+quote(t['table'])+' ('+cols+')')
  await conn.copy_to_table(t['table'],schema_name='commerce',source=str(DATA/(t['table']+'.copy')),format='binary')
 for kind in ('PRIMARY KEY','UNIQUE','FOREIGN KEY'):
  for t in manifest['tables']:
   for c in t['constraints']:
    if c['definition'].startswith(kind) and all(col in {v['name'] for v in t['columns']} for col in c.get('columns',[])):
     try: await conn.execute('ALTER TABLE commerce.'+quote(t['table'])+' ADD CONSTRAINT '+quote(c['name'])+' '+c['definition'])
     except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError): continue  # Private columns and out-of-scope tables are intentionally absent.
 reader=secrets.token_hex(24)
 await conn.execute("CREATE ROLE benchmark_reader LOGIN PASSWORD '"+reader+"'; GRANT USAGE ON SCHEMA commerce TO benchmark_reader; ALTER ROLE benchmark_reader SET default_transaction_read_only=on; ANALYZE")
 for t in manifest['tables']:
  privilege='SELECT' if t['full_select'] else 'SELECT ('+','.join(quote(c['name']) for c in t['columns'])+')'
  await conn.execute('GRANT '+privilege+' ON commerce.'+quote(t['table'])+' TO benchmark_reader')
 await conn.close()
 # Credentials remain in ignored local workspace, never in the benchmark artifacts.
 private=ROOT/'artifacts/local/dashboard-benchmark-connection.json'
 save(private, dict(url='postgresql://benchmark_reader:'+reader+'@127.0.0.1:55432/postgres',container=NAME))
 print('Snapshot ready:',sum(t['rows'] for t in manifest['tables']),'rows', flush=True)

if __name__=='__main__': asyncio.run(main())
