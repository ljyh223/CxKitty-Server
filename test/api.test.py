import unittest
from unittest.mock import patch, MagicMock
from cxapi.api import ChaoXingAPI

# cxapi/test_api.py


class TestChaoXingAPI(unittest.TestCase):

    def setUp(self):
        self.api = ChaoXingAPI()

    @patch('cxapi.api.SessionWraper.post')
    def test_login_passwd_success(self, mock_post):
        # Mocking the response to simulate a successful login
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": True}
        mock_post.return_value = mock_response

        phone = "17340307464"
        passwd = "jj123456"
        success, response = self.api.login_passwd(phone, passwd)
        print(response)
        self.assertTrue(success)
        self.assertEqual(response, {"status": True})

    @patch('cxapi.api.SessionWraper.post')
    def test_login_passwd_failure(self, mock_post):
        # Mocking the response to simulate a failed login
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": False}
        mock_post.return_value = mock_response

        phone = "1234567890"
        passwd = "wrongpassword"
        success, response = self.api.login_passwd(phone, passwd)

        print(response)
        self.assertFalse(success)
        self.assertEqual(response, {"status": False})

if __name__ == '__main__':
    unittest.main()