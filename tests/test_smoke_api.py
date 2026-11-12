import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from scripts.smoke_api import call_once, make_request, NoRedirect


class SmokeTests(unittest.TestCase):
    def test_json_probe_is_one_bounded_call_with_validated_action_and_usage(self):
        result = {"choices": [{"message": {"content": '{"action":"answer","answer":"OK"}'}}],
                  "usage": {"prompt_tokens": 20, "completion_tokens": 12}}
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(json.dumps(result).encode())
            output = call_once("https://api.neuraldeep.ru/v1", "test-token", "qwen3.8-27b-noreason", json_mode=True)
            body = json.loads(factory.return_value.open.call_args.args[0].data)
            self.assertEqual(body['response_format'], {'type': 'json_object'})
            self.assertEqual(body['max_tokens'], 32)
            self.assertTrue(output['json_action_valid'])
            self.assertTrue(output['usage_known'])
            self.assertEqual(output['weighted_tokens'], 14.0)
            self.assertEqual(output['status'], 'ok')
            factory.return_value.open.assert_called_once()

    def test_invalid_json_probe_retains_usage_and_sends_no_repair_call(self):
        for content, usage, status in [('I will answer OK.', {'prompt_tokens': 20, 'completion_tokens': 8}, 'unexpected_format'),
                                       ('{"action":"answer","answer":"OK"}', None, 'unexpected_usage')]:
            result = {'choices': [{'message': {'content': content}}], 'usage': usage}
            with self.subTest(status=status), patch('urllib.request.build_opener') as factory:
                factory.return_value.open.return_value = io.BytesIO(json.dumps(result).encode())
                output = call_once('https://api.neuraldeep.ru/v1', 'test-token', 'qwen3.8-27b-noreason', json_mode=True)
                self.assertEqual(output['status'], status)
                self.assertEqual(output['usage'], usage)
                factory.return_value.open.assert_called_once()

    def test_provider_rejection_of_json_mode_does_not_retry_without_the_flag(self):
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = urllib.error.HTTPError('url', 400, 'unsupported format', {}, None)
            with self.assertRaises(urllib.error.HTTPError):
                call_once('https://api.neuraldeep.ru/v1', 'test-token', 'qwen3.8-27b-noreason', json_mode=True)
            factory.return_value.open.assert_called_once()

    def test_invite_code_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            make_request("https://api.neuraldeep.ru/v1", "NGU26-EXAMPLE", "qwen3.8-27b-noreason")

    def test_single_bounded_request_and_usage(self):
        result = {"choices": [{"message": {"content": "OK"}}],
                  "usage": {"prompt_tokens": 14, "completion_tokens": 1}}
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = io.BytesIO(json.dumps(result).encode())
            output = call_once("https://api.neuraldeep.ru/v1/", "test-token", "qwen3.8-27b-noreason")
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.neuraldeep.ru/v1/chat/completions")
            self.assertEqual(json.loads(request.data)["max_tokens"], 32)
            self.assertEqual(output["answer"], "OK")
            self.assertEqual(output["usage"]["prompt_tokens"], 14)
            factory.return_value.open.assert_called_once()

    def test_error_does_not_trigger_a_retry(self):
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.side_effect = urllib.error.URLError("offline")
            with self.assertRaises(urllib.error.URLError):
                call_once("https://api.neuraldeep.ru/v1", "test-token", "qwen3.8-27b-noreason")
            factory.return_value.open.assert_called_once()

    def test_credentials_are_not_forwarded_on_redirect(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org"))

    def test_https_and_plain_url_required(self):
        for url in ("http://example.org", "https://user:pass@example.org", "https://example.org/?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                make_request(url, "test-token", "qwen3.8-27b-noreason")


if __name__ == "__main__":
    unittest.main()
