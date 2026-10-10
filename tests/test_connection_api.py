import sys
import unittest
from unittest.mock import patch
with patch.object(sys,'argv',['test','--no-debug']):
    import assistant as server
from browser_connection import BrowserConnection

class ApiTests(unittest.TestCase):
    def setUp(self):
        server.BROWSER=BrowserConnection()
        while not server.COMMANDS.empty():server.COMMANDS.get_nowait()
        server.RESULTS.clear();server.PENDING.clear()
        self.client=server.APP.test_client()
        r=self.client.post('/connect',json={'client_id':'test','protocol':2,'version':'1.15.0'})
        self.session=r.json['session']
    def poll(self):return self.client.get('/next',query_string={'client_id':'test','session':self.session})
    def result(self,rid,session=None):
        return self.client.post('/result',json={'client_id':'test','session':session or self.session,'request_id':rid,'result':{'ok':True}})
    def test_health(self):self.assertTrue(self.client.get('/health').json['connected'])
    def test_old_extension_cannot_poll(self):self.assertEqual(self.client.get('/next').status_code,409)
    def test_command_and_result(self):
        server.enqueue_browser({'tool':'media_control','action':'play','request_id':'r'})
        cmd=self.poll().json;self.assertEqual(cmd['session'],self.session)
        self.assertEqual(self.result('r').status_code,200)
        self.assertTrue(server.RESULTS['r']['ok']);self.assertEqual(self.result('r').status_code,409)
    def test_expired_queue_not_dispatched(self):
        server.enqueue_browser({'tool':'media_control','action':'play','request_id':'r'},timeout=-1)
        self.assertEqual(self.poll().json,{})
        self.assertEqual(server.RESULTS['r']['error'],'command_expired')
    def test_cancelled_wait_not_dispatched(self):
        server.enqueue_browser({'tool':'media_control','action':'play','request_id':'r'})
        server.expire_pending('r');self.assertEqual(self.poll().json,{})
    def test_old_result_rejected(self):
        server.enqueue_browser({'tool':'media_control','action':'play','request_id':'r'})
        self.assertEqual(self.result('r','old').status_code,409)
    def test_restart_changes_session(self):
        server.BROWSER=BrowserConnection();self.assertEqual(self.poll().status_code,409)
    def test_disconnect(self):
        self.assertTrue(self.client.post('/disconnect',json={'client_id':'test','session':self.session}).json['ok'])
        self.assertFalse(server.BROWSER.connected())
