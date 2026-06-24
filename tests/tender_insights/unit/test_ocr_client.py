from unittest.mock import MagicMock, patch

from tender_insights.common.ocr.client import OcrClient


def test_recognize_image_bytes_returns_model_text() -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="识别文字"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("tender_insights.common.ocr.client.OpenAI", return_value=mock_client):
        client = OcrClient(model="qwen-vl-ocr", api_key="k", base_url="http://test")
        text = client.recognize_image_bytes(b"fake", mime="image/png")

    assert text == "识别文字"
    mock_client.chat.completions.create.assert_called_once()
