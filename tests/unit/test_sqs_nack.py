import unittest
from unittest.mock import MagicMock, patch
from cocli.core.queue.sqs_queue import SQSQueue
from cocli.models.queue import QueueMessage

class TestSQSQueueNack(unittest.TestCase):
    def setUp(self):
        # Mock boto3 session and client
        self.boto3_patcher = patch('cocli.core.queue.sqs_queue.boto3')
        self.mock_boto3 = self.boto3_patcher.start()
        
        self.mock_sqs_client = MagicMock()
        self.mock_boto3.Session.return_value.client.return_value = self.mock_sqs_client
        
        self.queue = SQSQueue("https://sqs.us-east-1.amazonaws.com/123456789012/my-queue")

    def tearDown(self):
        self.boto3_patcher.stop()

    def test_nack_normal(self):
        msg = QueueMessage(domain="example.com", company_slug="example", campaign_name="test")
        msg.ack_token = "handle123"
        msg.attempts = 1
        
        self.queue.nack(msg, is_http_500=False)
        
        # Should change visibility to 0
        self.mock_sqs_client.change_message_visibility.assert_called_with(
            QueueUrl=self.queue.queue_url,
            ReceiptHandle="handle123",
            VisibilityTimeout=0
        )
        # Should NOT delete
        self.mock_sqs_client.delete_message.assert_not_called()

    def test_nack_http500_low_attempts(self):
        msg = QueueMessage(domain="example.com", company_slug="example", campaign_name="test")
        msg.ack_token = "handle123"
        msg.attempts = 2
        
        self.queue.nack(msg, is_http_500=True)
        
        # Should change visibility to 0 (retry)
        self.mock_sqs_client.change_message_visibility.assert_called_with(
            QueueUrl=self.queue.queue_url,
            ReceiptHandle="handle123",
            VisibilityTimeout=0
        )
        self.mock_sqs_client.delete_message.assert_not_called()

    def test_nack_http500_high_attempts(self):
        msg = QueueMessage(domain="example.com", company_slug="example", campaign_name="test")
        msg.ack_token = "handle123"
        msg.attempts = 3
        
        self.queue.nack(msg, is_http_500=True)
        
        # Should ACK (delete) instead of retry
        self.mock_sqs_client.delete_message.assert_called_with(
            QueueUrl=self.queue.queue_url,
            ReceiptHandle="handle123"
        )
        # Should NOT change visibility
        self.mock_sqs_client.change_message_visibility.assert_not_called()

if __name__ == '__main__':
    unittest.main()
