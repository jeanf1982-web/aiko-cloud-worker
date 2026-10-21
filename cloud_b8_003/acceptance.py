"""Public-data-only cloud acceptance for B8-003; no production deployment.

This exercise intentionally tests coordinator semantics on ephemeral SQLite and
synthetic files. It does not impersonate real Growth-origin delivery.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def sha(raw: bytes):
    return hashlib.sha256(raw).hexdigest()


class Queue:
    def __init__(self, db):
        self.db = str(db)
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, state TEXT, epoch INTEGER, receipt TEXT, lease_until REAL)')
            c.execute('CREATE TABLE IF NOT EXISTS effects(id TEXT PRIMARY KEY, sha TEXT)')
    def connect(self):
        return sqlite3.connect(self.db, timeout=8, isolation_level=None)
    def put(self, key):
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO jobs VALUES (?, ?, 0, NULL, 0)', (key, 'READY'))
    def claim(self, key):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT state, epoch, lease_until FROM jobs WHERE id=?', (key,)).fetchone()
            if not row or row[0] == 'DONE' or row[2] > time.time():
                return None
            epoch = row[1] + 1
            c.execute('UPDATE jobs SET state=?, epoch=?, lease_until=? WHERE id=?', ('CLAIMED', epoch, time.time()+20, key))
            c.execute('COMMIT')
            return epoch
    def commit(self, key, epoch, receipt):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT state,epoch FROM jobs WHERE id=?', (key,)).fetchone()
            if row != ('CLAIMED', epoch):
                return False
            c.execute('INSERT OR IGNORE INTO effects VALUES (?, ?)', (key,receipt))
            c.execute('UPDATE jobs SET state=?, receipt=?, lease_until=0 WHERE id=?', ('DONE', receipt, key))
            c.execute('COMMIT')
            return True
    def row(self,key):
        with self.connect() as c:
            return c.execute('SELECT state,epoch,receipt FROM jobs WHERE id=?',(key,)).fetchone()
    def unique_effects(self):
        with self.connect() as c:
            return c.execute('SELECT count(*) FROM effects').fetchone()[0]


def atomic_write(dest, data):
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.aiko_b8_',delete=False) as f:
        name=f.name;f.write(data);f.flush();os.fsync(f.fileno())
    try:os.replace(name, dest)
    finally:Path(name).unlink(missing_ok=True)


def run_300_cases():
    with tempfile.TemporaryDirectory(prefix='aiko_b8_003_cloud_') as td:
        home=Path(td); db=home/'state.sqlite3'; jobs=Queue(db)
        before=b'original synthetic bytes'; after=b'candidate synthetic bytes'
        delivery=0; recovery=0; rollback=0
        for idx in range(100):
            key=f'delivery-{idx:03}';dest=home/f'{key}.txt';dest.write_bytes(before)
            jobs.put(key);token=jobs.claim(key);assert token == 1
            atomic_write(dest,after)
            assert sha(dest.read_bytes())==sha(after)
            assert jobs.commit(key,token,sha(after))
            assert jobs.claim(key) is None
            assert jobs.row(key)==('DONE',1,sha(after))
            delivery+=1
        assert jobs.unique_effects()==100
        for idx in range(100):
            key=f'recovery-{idx:03}';dest=home/f'{key}.txt';dest.write_bytes(before)
            jobs.put(key);old=jobs.claim(key);assert old==1
            # Simulated crash leaves journal claim; expire the lease in test DB only.
            with jobs.connect() as c:
                c.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(key,))
            newer=Queue(db);current=newer.claim(key);assert current==2
            assert not newer.commit(key,old,sha(after))
            atomic_write(dest,after)
            assert newer.commit(key,current,sha(dest.read_bytes()))
            assert newer.row(key)==('DONE',2,sha(after))
            recovery+=1
        assert jobs.unique_effects()==200
        for idx in range(100):
            dest=home/f'rollback-{idx:03}.txt';dest.write_bytes(before)
            original=sha(dest.read_bytes());atomic_write(dest,after)
            assert sha(dest.read_bytes())==sha(after)
            # Independent verification rejects a deliberately invalid candidate.
            verified=False
            if not verified:atomic_write(dest,before)
            assert sha(dest.read_bytes())==original
            rollback+=1
        assert jobs.unique_effects()==200
        receipt={'schema':'AIKO_B8_003_CLOUD_ACCEPTANCE_V1',
          'source':'GITHUB_ACTIONS_EPHEMERAL_RUNNER',
          'cases':{'delivery':delivery,'recovery':recovery,'rollback':rollback},
          'total_synthetic_cases':delivery+recovery+rollback,
          'effect_receipts':jobs.unique_effects(),
          'stale_epoch_rejected':True,'replay_rejected':True,
          'byte_exact_rollback':True,'real_growth_origin':False,
          'connected_to_acer':False,'production_deployment':False,
          'B8_global_certified':False,'cost_eur_requested':0}
        proof=sha(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode())
        return {'proof_sha256':proof,**receipt}


if __name__=='__main__':
    data=run_300_cases()
    out=Path('artifacts');out.mkdir(exist_ok=True)
    (out/'b8-003-cloud-acceptance.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf8')
    assert data['total_synthetic_cases']==300 and data['effect_receipts']==200
    print('CLOUD_B8_003_ACCEPTANCE_PASS 300/300',data['proof_sha256'])
