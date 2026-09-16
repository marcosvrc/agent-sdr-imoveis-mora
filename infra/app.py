"""Uma stack por domínio. Ordem de dependência: network → data → ai → messaging → agent → channels → api → frontend."""
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.data_stack import DataStack
from stacks.ai_stack import AiStack
from stacks.messaging_stack import MessagingStack
from stacks.agent_stack import AgentStack
from stacks.channels_stack import ChannelsStack
from stacks.scheduler_stack import SchedulerStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack
from stacks.observability_stack import ObservabilityStack

app = cdk.App()
env_name = app.node.try_get_context("env")
env = cdk.Environment(region=app.node.try_get_context("region"))
p = f"sdr-{env_name}"

net = NetworkStack(app, f"{p}-network", env=env)
data = DataStack(app, f"{p}-data", vpc=net.vpc, lambda_sg=net.lambda_sg, env=env)
ai = AiStack(app, f"{p}-ai", cluster=data.cluster, bucket=data.bucket, env=env)
msg = MessagingStack(app, f"{p}-messaging", env=env)
sch = SchedulerStack(app, f"{p}-scheduler", queues=msg, env=env)
agent = AgentStack(app, f"{p}-agent", vpc=net.vpc, lambda_sg=net.lambda_sg, cluster=data.cluster, queues=msg, ai=ai, scheduler_role_arn=sch.role_arn, env=env)
channels = ChannelsStack(app, f"{p}-channels", queues=msg, vpc=net.vpc, lambda_sg=net.lambda_sg, cluster=data.cluster, env=env)
api = ApiStack(app, f"{p}-api", vpc=net.vpc, lambda_sg=net.lambda_sg, cluster=data.cluster, queues=msg, env=env)
FrontendStack(app, f"{p}-frontend", api_url=api.url, ws_url=channels.ws_url, env=env)
ObservabilityStack(app, f"{p}-observability", env=env)

app.synth()
