from aws_cdk import Stack, CfnOutput, aws_iam as iam, aws_scheduler as scheduler
from constructs import Construct


class SchedulerStack(Stack):
    """Follow-up: o agent cria schedules one-shot (EventBridge Scheduler → SQS inbound) via shared/adapters/aws/scheduler.py.
    Aqui só o grupo de schedules e a role que o Scheduler assume para publicar na fila."""
    def __init__(self, scope: Construct, id: str, queues, **kw):
        super().__init__(scope, id, **kw)
        group = scheduler.CfnScheduleGroup(self, "Group", name="sdr-followup")
        role = iam.Role(self, "SchedulerRole", assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"))
        queues.inbound.grant_send_messages(role)
        self.role_arn, self.group_name = role.role_arn, group.name
        CfnOutput(self, "SchedulerRoleArn", value=role.role_arn)
