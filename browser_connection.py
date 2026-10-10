"""Controller lease and per-start session identity; no browser commands survive expiry."""
import threading
import time
import uuid

PROTOCOL=2
LEASE_SECONDS=45
MIN_EXTENSION='1.15.0'


class BrowserConnection:
    def __init__(self, clock=time.monotonic):
        self.clock=clock
        self.session=str(uuid.uuid4())
        self.client=None
        self.last_seen=0
        self.version=None
        self.lock=threading.Lock()
        self.changed=threading.Condition(self.lock)

    def connected(self):
        with self.lock:return self.client is not None and self.clock()-self.last_seen<LEASE_SECONDS

    def connect(self, client, protocol, version):
        if not isinstance(client,str) or not client or len(client)>100:return {'ok':False,'error':'invalid_client'}
        if protocol!=PROTOCOL:return {'ok':False,'error':'extension_update_required','required_version':MIN_EXTENSION}
        with self.changed:
            if self.client and self.client!=client and self.clock()-self.last_seen<LEASE_SECONDS:
                return {'ok':False,'error':'controller_already_connected'}
            self.client=client;self.last_seen=self.clock();self.version=version
            self.changed.notify_all()
            return {'ok':True,'session':self.session,'protocol':PROTOCOL}

    def authorised(self, client, session):
        with self.lock:
            return bool(self.client and client==self.client and session==self.session and self.clock()-self.last_seen<LEASE_SECONDS)

    def wait(self, timeout=1):
        with self.changed:
            return self.changed.wait_for(lambda:self.client is not None and self.clock()-self.last_seen<LEASE_SECONDS,timeout)

    def touch(self,client,session):
        with self.changed:
            if not self.client or client!=self.client or session!=self.session or self.clock()-self.last_seen>=LEASE_SECONDS:return False
            self.last_seen=self.clock();self.changed.notify_all();return True

    def disconnect(self,client,session):
        with self.changed:
            if client==self.client and session==self.session:
                self.client=None;self.changed.notify_all();return True
            return False
