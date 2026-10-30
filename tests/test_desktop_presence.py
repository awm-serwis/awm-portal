import os, tempfile, unittest
class PresenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from portal_app import app, API_KEY
        cls.app=app
        cls.key=API_KEY
        cls.app.testing=True
    def setUp(self):self.client=self.app.test_client()
    def test_heartbeat_auth_and_status(self):
        self.assertEqual(self.client.post("/api/awm-desktop/heartbeat").status_code,403)
        self.assertEqual(self.client.post("/api/awm-desktop/heartbeat",headers={"X-AWM-Key":"wrong"}).status_code,403)
        self.assertEqual(self.client.get("/api/awm-desktop/status").status_code,401)
        self.assertEqual(self.client.post("/api/login",json={"login":"AWM","password":os.getenv("AWM_ADMIN_PASS","AWM-START-2026")}).status_code,200)
        self.assertFalse(self.client.get("/api/awm-desktop/status").json["online"])
        self.assertEqual(self.client.post("/api/awm-desktop/heartbeat",headers={"X-AWM-Key":self.key}).status_code,200)
        self.assertTrue(self.client.get("/api/awm-desktop/status").json["online"])
        from portal_app import DATA
        import sqlite3
        c=sqlite3.connect(str(DATA/"desktop_presence.db"))
        c.execute("UPDATE heartbeat SET timestamp=0 WHERE id=1");c.commit();c.close()
        self.assertFalse(self.client.get("/api/awm-desktop/status").json["online"])
    def test_no_web_history(self):
        self.assertEqual(self.client.get("/admin/dostep").status_code,404)
        self.assertEqual(self.client.get("/api/admin/access-events").status_code,403)
        self.assertEqual(self.client.get("/api/admin/access-events",headers={"X-AWM-Key":self.key}).status_code,200)
        h=self.client.get("/").data.decode()
        self.assertNotIn("awmAccessAdminLink",h)
        self.assertIn("awmTopLogout",h)
        self.assertIn("AWM OFFLINE",h)
if __name__=="__main__": unittest.main()
