import json
import logging
from typing import List, Optional
from botocore.exceptions import ClientError

from ...models.command import CocliCommand

logger = logging.getLogger(__name__)

class CommandSQSQueue:
    """
    AWS SQS based queue implementation for remote CLI commands.
    """

    def __init__(self, queue_url: str, aws_profile_name: Optional[str] = None, region_name: str = "us-east-1"):
        self.queue_url = queue_url
        
        try:
            from ..reporting import get_boto3_session
            # Mock a config dict for the session creator
            config = {"aws": {"profile": aws_profile_name, "region": region_name}}
            session = get_boto3_session(config)
            self.sqs = session.client("sqs", region_name=region_name)
        except Exception as e:
            logger.error(f"Failed to create SQS client: {e}")
            raise

    def poll(self, batch_size: int = 1) -> List[CocliCommand]:
        """
        Retrieve a batch of commands from SQS.
        """
        commands: List[CocliCommand] = []
        try:
            response = self.sqs.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(batch_size, 10),
                WaitTimeSeconds=20, # Max long polling
                AttributeNames=['ApproximateReceiveCount']
            )

            if 'Messages' in response:
                for sqs_msg in response['Messages']:
                    try:
                        body = sqs_msg['Body']
                        data = json.loads(body)
                        
                        # Handle both direct list of args or structured object
                        if isinstance(data, list):
                            # Backward compat or simple case
                            cmd = CocliCommand(
                                command=" ".join(data), 
                                args=data, 
                                campaign=None, 
                                ack_token=sqs_msg['ReceiptHandle']
                            )
                        elif isinstance(data, dict) and "command" in data:
                            cmd = CocliCommand(
                                command=data["command"],
                                args=data.get("args"),
                                campaign=data.get("campaign"),
                                ack_token=sqs_msg['ReceiptHandle']
                            )
                        else:
                            logger.error(f"Invalid command message format: {data}")
                            continue
                        
                        commands.append(cmd)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"Error parsing command SQS message body: {e}")
        except ClientError as e:
            logger.error(f"Error polling command SQS: {e}")
        
        return commands

    def ack(self, command: CocliCommand) -> None:
        """Delete the command message from SQS."""
        if not command.ack_token:
            return
        try:
            self.sqs.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=command.ack_token
            )
        except ClientError as e:
            logger.error(f"Error acking command: {e}")
