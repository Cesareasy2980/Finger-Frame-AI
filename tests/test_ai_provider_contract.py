import unittest

from google import genai

from stylize import MODEL, build_interaction_input


class AIProviderContractTests(unittest.TestCase):
    def test_model_and_request_shape_match_existing_provider_path(self):
        self.assertEqual(MODEL, "gemini-omni-flash-preview")
        self.assertEqual(
            build_interaction_input("https://example.invalid/video", "style prompt"),
            [
                {"type": "document", "uri": "https://example.invalid/video"},
                {"type": "text", "text": "style prompt"},
            ],
        )

    def test_pinned_sdk_exposes_required_clients_without_network(self):
        client = genai.Client(api_key="milestone-zero-placeholder")
        self.assertTrue(callable(client.files.upload))
        self.assertTrue(callable(client.files.get))
        self.assertTrue(callable(client.files.download))
        self.assertTrue(callable(client.interactions.create))
        self.assertTrue(callable(client.interactions.get))
        self.assertTrue(callable(client.models.get))


if __name__ == "__main__":
    unittest.main()
