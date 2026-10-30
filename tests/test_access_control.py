import os
import tempfile
import unittest
from unittest.mock import patch

class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        os.environ["AWM_DATA_DIR"]=cls.tmp.name
        os.environ["AWM_API_KEY"]="test-key-for-local-ci-only"
        os.environ["AWM_SECRET_KEY"]="test-session-key-for-local-ci"
        os.environ.pop("SUPABASE_URL",None)
        os.environ.pop("SUPABASE_SECRET_KEY",None)
        from portal_app import app
        cls.app=app
        cls.app.testing=True

    # Keep temporary database until entire unittest discovery ends.
    # The presence test class uses the same imported Flask app and database.

    def setUp(self):
        self.client=self.app.test_client()
        self.key={"X-AWM-Key":"test-key-for-local-ci-only"}

    def test_reviewers_create_edit_block_and_audit(self):
        r=self.client.post("/api/admin/access-users",json={"login":"marsta","password":"abcdef","label":"Marcin"},headers=self.key)
        self.assertEqual(r.status_code,201)
        users=self.client.get("/api/admin/access-users",headers=self.key).get_json()["users"]
        account=next(u for u in users if u["login"]=="marsta")
        self.assertEqual(account["label"],"Marcin")
        self.assertEqual(account["role"],"reviewer")
        self.assertEqual(self.client.post("/api/login",json={"login":"marsta","password":"abcdef"}).status_code,200)
        self.assertEqual(self.client.get("/api/vehicles").status_code,200)
        self.assertEqual(self.client.patch("/api/admin/access-users",json={"id":account["id"],"action":"disable"},headers=self.key).status_code,200)
        self.assertEqual(self.client.get("/api/vehicles").status_code,401)
        self.assertEqual(self.client.post("/api/login",json={"login":"marsta","password":"abcdef"}).status_code,401)
        self.assertEqual(self.client.patch("/api/admin/access-users",json={"id":account["id"],"action":"enable"},headers=self.key).status_code,200)
        self.assertEqual(self.client.patch("/api/admin/access-users",json={"id":account["id"],"action":"password","password":"newpass"},headers=self.key).status_code,200)
        self.assertEqual(self.client.post("/api/login",json={"login":"marsta","password":"newpass"}).status_code,200)
        events=self.client.get("/api/admin/access-events",headers=self.key).get_json()["events"]
        self.assertTrue(any(e["event"]=="account_disable" for e in events))
        self.assertTrue(any(e["event"]=="login" for e in events))

    def test_invalid_and_unauthorized(self):
        self.assertEqual(self.client.get("/api/admin/access-users").status_code,403)
        self.assertEqual(self.client.post("/api/admin/access-users",json={"login":"wrong","password":"123456"},headers={"X-AWM-Key":"bad"}).status_code,403)
        self.assertEqual(self.client.post("/api/admin/access-users",json={"login":"test2","password":"123"},headers=self.key).status_code,400)
        self.assertEqual(self.client.get("/admin/dostep").status_code,404)

    def test_portal_and_workshop_routes(self):
        self.assertEqual(self.client.get("/").status_code,200)
        self.assertEqual(self.client.get("/health").status_code,200)
        self.assertEqual(self.client.get("/warsztat").status_code,403)
        self.assertEqual(self.client.post("/api/login",json={"login":"AWM","password":os.getenv("AWM_ADMIN_PASS","AWM-START-2026")}).status_code,200)
        self.assertEqual(self.client.get("/warsztat").status_code,200)
        self.assertEqual(self.client.get("/admin/dostep").status_code,404)

if __name__=="__main__":
    unittest.main()
