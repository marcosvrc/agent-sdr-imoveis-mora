import os
import boto3
from datetime import datetime, timedelta, timezone
from ...config import get_settings


class EventBridgeScheduler:
    def __init__(self):
        self._c = boto3.client("scheduler"); self._group = get_settings().scheduler_group

    def schedule(self, lead_id: str, delay_min: int, payload: str) -> None:
        quando = (datetime.now(timezone.utc) + timedelta(minutes=delay_min)).strftime("%Y-%m-%dT%H:%M:%S")
        args = dict(Name=f"followup-{lead_id}", GroupName=self._group, ScheduleExpression=f"at({quando})",
                    FlexibleTimeWindow={"Mode": "OFF"}, ActionAfterCompletion="DELETE",
                    Target={"Arn": os.environ["INBOUND_QUEUE_ARN"], "RoleArn": os.environ["SCHEDULER_ROLE_ARN"],
                            "SqsParameters": {"MessageGroupId": lead_id}, "Input": payload})
        try:
            self._c.update_schedule(**args)
        except self._c.exceptions.ResourceNotFoundException:
            self._c.create_schedule(**args)

    def cancel(self, lead_id: str) -> None:
        try:
            self._c.delete_schedule(Name=f"followup-{lead_id}", GroupName=self._group)
        except self._c.exceptions.ResourceNotFoundException:
            pass
