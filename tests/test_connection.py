import unittest
from browser_connection import BrowserConnection,PROTOCOL

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.now=1;self.c=BrowserConnection(clock=lambda:self.now)
    def connect(self,client='a'):return self.c.connect(client,PROTOCOL,'1.15.0')
    def test_handshake_and_expiry(self):
        self.assertFalse(self.c.connected());self.assertTrue(self.connect()['ok'])
        self.assertTrue(self.c.connected());self.now+=46;self.assertFalse(self.c.connected())
    def test_duplicate_rejected_then_recover(self):
        self.connect();self.assertFalse(self.connect('b')['ok'])
        self.now+=46;self.assertTrue(self.connect('b')['ok'])
    def test_old_session_rejected(self):
        self.connect();self.assertFalse(self.c.authorised('a','old-session'))
        self.assertTrue(self.c.authorised('a',self.c.session))
    def test_poll_refresh(self):
        self.connect();self.now+=30;self.assertTrue(self.c.touch('a',self.c.session))
        self.now+=30;self.assertTrue(self.c.connected())
    def test_disconnect_owner_only(self):
        self.connect();self.assertFalse(self.c.disconnect('b',self.c.session))
        self.assertTrue(self.c.disconnect('a',self.c.session));self.assertFalse(self.c.connected())
    def test_old_protocol_rejected(self):
        self.assertEqual(self.c.connect('a',1,'old')['error'],'extension_update_required')
