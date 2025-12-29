import json
import logging
from typing import List, Optional
import boto3
from botocore.exceptions import ClientError

from ...models.scrape_task import GmItemTask

logger = logging.getLogger(__name__)

class GmItemSQSQueue:
    """
    AWS SQS based queue implementation for GmItemTask.
    """

    def __init__(self, queue_url: str, aws_profile_name: Optional[str] = None, region_name: str = "us-east-1"):
        self.queue_url = queue_url
        
        try:
            if aws_profile_name:
                session = boto3.Session(profile_name=aws_profile_name, region_name=region_name)
            else:
                session = boto3.Session(region_name=region_name)
            self.sqs = session.client("sqs")
        except Exception as e:
            logger.error(f"Failed to create SQS client: {e}")
            raise

    def push(self, message: GmItemTask) -> str:
        """Push a message to the SQS queue."""
        try:
            response = self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=message.model_dump_json(exclude={'ack_token'})
            )
            return str(response.get('MessageId', ''))
        except ClientError as e:
            logger.error(f"Error pushing to SQS: {e}")
            raise

    def poll(self, batch_size: int = 1) -> List[GmItemTask]:
        """
        Retrieve a batch of messages from SQS.
        """
        messages: List[GmItemTask] = []
        try:
            response = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(batch_size, 10), # SQS max is 10
                WaitTimeSeconds=5, # Long polling
                AttributeNames=['ApproximateReceiveCount']
            )

            if 'Messages' in response:
                for sqs_msg in response['Messages']:
                    try:
                        body = sqs_msg['Body']
                        data = json.loads(body)
                        
                        # Deserialize
                        task = GmItemTask(**data)
                        
                        # Attach ReceiptHandle for ACK
                        task.ack_token = sqs_msg['ReceiptHandle']
                        
                        # Update attempts from SQS metadata if available
                        if 'Attributes' in sqs_msg and 'ApproximateReceiveCount' in sqs_msg['Attributes']:
                            task.attempts = int(sqs_msg['Attributes']['ApproximateReceiveCount'])

                        messages.append(task)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"Error parsing SQS message body: {e}")
        except ClientError as e:
            logger.error(f"Error polling SQS: {e}")
        
        return messages

    def ack(self, message: GmItemTask) -> None:
        """
        Delete the message from SQS.
        """
        if not message.ack_token:
            logger.warning("Cannot ack task: No receipt handle (ack_token).")
            return

        try:
            self.sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=message.ack_token
            )
            logger.debug("Acked SQS task")
        except ClientError as e:
            logger.error(f"Error acking SQS task: {e}")

    def nack(self, message: GmItemTask) -> None:
        """
        Change visibility timeout to 0 to make it immediately available again.
        """
        if not message.ack_token:
            logger.warning("Cannot nack task: No receipt handle (ack_token).")
            return

        try:
            self.sqs.change_message_visibility(
                QueueUrl=self.queue_url,
                ReceiptHandle=message.ack_token,
                VisibilityTimeout=0
            )
            logger.info("Nacked SQS task (Visibility -> 0)")
        except ClientError as e:
            logger.error(f"Error nacking SQS task: {e}")
