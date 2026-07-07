import unittest
from unittest.mock import patch, MagicMock, mock_open, Mock
import sys
import os
import json
import base64

# Make sure that "src" is known and can be used to import rp_handler.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from src import rp_handler

# Local folder for test resources
RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES = "./test_resources/images"


class TestRunpodWorkerComfy(unittest.TestCase):
    def test_valid_input_with_workflow_only(self):
        input_data = {"workflow": {"key": "value"}}
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, {"download_file_names": [], "workflow": {"key": "value"}, "images": None})

    def test_valid_input_with_workflow_and_images(self):
        input_data = {
            "download_file_names": [],
            "workflow": {"key": "value"},
            "images": [{"name": "image1.png", "image": "base64string"}],
        }
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, input_data)

    def test_input_missing_workflow(self):
        input_data = {"images": [{"name": "image1.png", "image": "base64string"}]}
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Missing 'workflow' parameter")

    def test_input_with_invalid_images_structure(self):
        input_data = {
            "workflow": {"key": "value"},
            "images": [{"name": "image1.png"}],  # Missing 'image' key
        }
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(
            error, "'images' must be a list of objects with 'name' and 'image' keys"
        )

    def test_invalid_json_string_input(self):
        input_data = "invalid json"
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Invalid JSON format in input")

    def test_valid_json_string_input(self):
        input_data = '{"workflow": {"key": "value"}}'
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNone(error)
        self.assertEqual(validated_data, {"download_file_names": [], "workflow": {"key": "value"}, "images": None})

    def test_empty_input(self):
        input_data = None
        validated_data, error = rp_handler.validate_input(input_data)
        self.assertIsNotNone(error)
        self.assertEqual(error, "Please provide input")

    @patch("rp_handler.requests.get")
    def test_check_server_server_up(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.return_value = mock_response

        result = rp_handler.check_server("http://127.0.0.1:8188", 1, 50)
        self.assertTrue(result)

    @patch("rp_handler.requests.get")
    def test_check_server_server_down(self, mock_requests):
        mock_requests.get.side_effect = rp_handler.requests.RequestException()
        result = rp_handler.check_server("http://127.0.0.1:8188", 1, 50)
        self.assertFalse(result)

    @patch("rp_handler.urllib.request.urlopen")
    def test_queue_prompt(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"prompt_id": "123"}).encode()
        mock_urlopen.return_value = mock_response
        result = rp_handler.queue_workflow({"prompt": "test"})
        self.assertEqual(result, {"prompt_id": "123"})

    @patch("rp_handler.urllib.request.urlopen")
    def test_get_history(self, mock_urlopen):
        # Mock response data as a JSON string
        mock_response_data = json.dumps({"key": "value"}).encode("utf-8")

        # Define a mock response function for `read`
        def mock_read():
            return mock_response_data

        # Create a mock response object
        mock_response = Mock()
        mock_response.read = mock_read

        # Mock the __enter__ and __exit__ methods to support the context manager
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = Mock()

        # Set the return value of the urlopen mock
        mock_urlopen.return_value = mock_response

        # Call the function under test
        result = rp_handler.get_history("123")

        # Assertions
        self.assertEqual(result, {"key": "value"})
        mock_urlopen.assert_called_with("http://127.0.0.1:8188/history/123")

    @patch("builtins.open", new_callable=mock_open, read_data=b"test")
    def test_base64_encode(self, mock_file):
        test_data = base64.b64encode(b"test").decode("utf-8")

        result = rp_handler.base64_encode("dummy_path")

        self.assertEqual(result, test_data)

    @patch("rp_handler.os.path.exists")
    @patch("src.rp_handler.runpod_upload_image")
    @patch.dict(
        os.environ, {"COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES}
    )
    def test_bucket_endpoint_not_configured(self, mock_upload_image, mock_exists):
        mock_exists.return_value = True
        mock_upload_image.return_value = "simulated_uploaded/image.png"

        outputs = {
            "node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}
        }
        job_id = "123"

        result = rp_handler.process_output_images(outputs, job_id, [])

        self.assertEqual(result["status"], "success")

    @patch("rp_handler.os.path.exists")
    @patch("src.rp_handler.runpod_upload_image")
    @patch.dict(
        os.environ,
        {
            "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
            "BUCKET_ENDPOINT_URL": "http://example.com",
        },
    )
    def test_bucket_endpoint_configured(self, mock_upload_image, mock_exists):
        # Mock the os.path.exists to return True, simulating that the image exists
        mock_exists.return_value = True

        mock_upload_image.return_value = (
            "http://example.com/uploaded/image.png",
            "runpod-temp/123/image.png",
        )

        # Define the outputs and job_id for the test
        outputs = {"node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": "test"}]}}
        job_id = "123"

        # Call the function under test
        result = rp_handler.process_output_images(outputs, job_id, [])

        # Assertions
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            result["message"],
            [{
                "url": "http://example.com/uploaded/image.png",
                "obj_key": "runpod-temp/123/image.png",
            }],
        )
        mock_upload_image.assert_called_once()
        upload_args, upload_kwargs = mock_upload_image.call_args
        self.assertEqual(upload_args[0], job_id)
        self.assertEqual(
            os.path.normpath(upload_args[1]),
            os.path.normpath(os.path.join("./test_resources/images", "test", "ComfyUI_00001_.png")),
        )
        self.assertEqual(upload_kwargs, {"bucket_name": "runpod-temp"})

    @patch("src.rp_handler.runpod_upload_image")
    @patch.dict(
        os.environ,
        {
            "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
            "BUCKET_ENDPOINT_URL": "http://example.com",
        },
    )
    def test_text_file_output_is_uploaded_from_comfy_history_files(self, mock_upload_file):
        text_dir = os.path.join(RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES, "FireOCR")
        os.makedirs(text_dir, exist_ok=True)
        text_path = os.path.join(text_dir, "fire_ocr_test.txt")
        with open(text_path, "w", encoding="utf-8") as file:
            file.write("recognized text")
        mock_upload_file.return_value = (
            "http://example.com/uploaded/fire_ocr_test.txt",
            "runpod-temp/123/fire_ocr_test.txt",
        )

        outputs = {
            "node_id": {
                "files": [{"filename": "fire_ocr_test.txt", "subfolder": "FireOCR"}],
            }
        }
        job_id = "123"

        try:
            result = rp_handler.process_output_images(outputs, job_id, [])
        finally:
            os.remove(text_path)

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            result["message"],
            [{
                "url": "http://example.com/uploaded/fire_ocr_test.txt",
                "obj_key": "runpod-temp/123/fire_ocr_test.txt",
            }],
        )
        mock_upload_file.assert_called_once()
        upload_args, upload_kwargs = mock_upload_file.call_args
        self.assertEqual(upload_args[0], job_id)
        self.assertEqual(
            os.path.normpath(upload_args[1]),
            os.path.normpath(os.path.join("./test_resources/images", "FireOCR", "fire_ocr_test.txt")),
        )
        self.assertEqual(upload_kwargs, {"bucket_name": "runpod-temp"})

    @patch("rp_handler.os.path.exists")
    @patch("src.rp_handler.runpod_upload_image")
    @patch.dict(
        os.environ,
        {
            "COMFY_OUTPUT_PATH": RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES,
            "BUCKET_ENDPOINT_URL": "http://example.com",
            "BUCKET_ACCESS_KEY_ID": "",
            "BUCKET_SECRET_ACCESS_KEY": "",
        },
    )
    def test_bucket_image_upload_fails_env_vars_wrong_or_missing(
        self, mock_upload_image, mock_exists
    ):
        # Simulate the file existing in the output path
        mock_exists.return_value = True

        mock_upload_image.return_value = (
            "simulated_uploaded/image.png",
            "simulated_uploaded/image.png",
        )

        outputs = {
            "node_id": {"images": [{"filename": "ComfyUI_00001_.png", "subfolder": ""}]}
        }
        job_id = "123"

        result = rp_handler.process_output_images(outputs, job_id, [])

        # Check if the image was saved to the 'simulated_uploaded' directory
        self.assertIn("simulated_uploaded", result["message"][0]["url"])
        self.assertEqual(result["status"], "success")

    @patch("rp_handler.requests.post")
    def test_upload_images_successful(self, mock_post):
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "Successfully uploaded"
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")

        images = [{"name": "test_image.png", "image": test_image_data}]

        responses = rp_handler.upload_images(images)

        self.assertEqual(len(responses), 3)
        self.assertEqual(responses["status"], "success")

    @patch("rp_handler.requests.post")
    def test_upload_images_failed(self, mock_post):
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Error uploading"
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")

        images = [{"name": "test_image.png", "image": test_image_data}]

        responses = rp_handler.upload_images(images)

        self.assertEqual(len(responses), 3)
        self.assertEqual(responses["status"], "error")
